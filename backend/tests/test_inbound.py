"""Orders arriving from outside, end to end.

The whole path, with no network: a raw email or a Telegram update goes in, the
Smart Input engine parses it, it waits in the review queue, a person accepts it,
and a real sale exists with stock moved. The channel adapters are exercised
against their real payload shapes — an RFC-822 message and a Telegram `getUpdates`
response — rather than against a convenient stub.

The safety property these mostly protect: **nothing external writes to the books
on its own.** Every test that records something records it through an accept
call made by a signed-in user.
"""

from __future__ import annotations

import uuid
from email.message import EmailMessage

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.inbound import email as email_channel
from app.inbound import telegram as telegram_channel
from app.inbound.collector import _link_chat
from app.inbound.pipeline import ingest
from app.models import Business, ChannelLink, InboundMessage


@pytest.fixture
def business_id(client) -> uuid.UUID:
    return uuid.UUID(client.get("/api/auth/me").json()["business"]["id"])


@pytest.fixture
def inbox_token(client) -> str:
    return client.get("/api/inbox").json()["inboxToken"]


@pytest.fixture(autouse=True)
def clean_queue():
    """Each test starts with an empty queue and no channel links."""
    yield
    with SessionLocal() as db:
        db.query(InboundMessage).delete()
        db.query(ChannelLink).delete()
        db.commit()


def _raw_email(
    to: str, subject: str, body: str, sender: str = "Anita <anita@example.com>"
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = f"<{uuid.uuid4().hex}@example.com>"
    message.set_content(body)
    return message.as_bytes()


def _deliver(db, raw: bytes) -> InboundMessage | None:
    parsed = email_channel.to_incoming(raw, fallback_id="test")
    assert parsed is not None
    return ingest(db, parsed)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def test_an_emailed_order_is_parsed_into_a_draft(client, workspace, inbox_token):
    with SessionLocal() as db:
        row = _deliver(
            db,
            _raw_email(
                f"orders+{inbox_token}@smartsme.local",
                "Order for tomorrow",
                "Please send 4 Cooking Oil to Anita Stores",
            ),
        )
        assert row is not None
        assert row.status == "pending"
        assert row.sender == "anita@example.com"
        assert row.draft["suggestedType"] == "sale"
        assert row.draft["items"][0]["quantity"] == 4


def test_the_subject_is_read_as_well_as_the_body(client, workspace, inbox_token):
    """Shopkeepers put the whole order in the subject line and leave the body
    empty, or the other way round."""
    with SessionLocal() as db:
        row = _deliver(
            db,
            _raw_email(
                f"orders+{inbox_token}@smartsme.local",
                "Need 7 Cooking Oil for Anita Stores",
                "Thanks!",
            ),
        )
        assert row.draft["items"][0]["quantity"] == 7


def test_a_kannada_order_reaches_the_right_customer(client, workspace, inbox_token):
    """A Kannada order should not merely survive the trip - it should land on
    the customer it names. The workspace customer is "Anita Stores"; the mail
    says ಅನಿತಾ, which is the same name in another alphabet."""
    with SessionLocal() as db:
        row = _deliver(
            db,
            _raw_email(
                f"orders+{inbox_token}@smartsme.local",
                "ಆರ್ಡರ್",
                "ಅನಿತಾಗೆ ೬ ಕಿಲೋ ಅಕ್ಕಿ ಬೇಕು",
            ),
        )
        assert row.status == "pending"
        assert row.draft["partyId"] == workspace["customerId"], row.draft["partyName"]
        assert row.draft["partyName"] == "Anita Stores"
        assert row.draft["items"][0]["quantity"] == 6


def test_an_unknown_kannada_name_is_kept_as_written(client, workspace, inbox_token):
    """Nothing to resolve to, so the name is passed through for the person
    reviewing rather than guessed at or dropped."""
    with SessionLocal() as db:
        row = _deliver(
            db,
            _raw_email(
                f"orders+{inbox_token}@smartsme.local",
                "ಆರ್ಡರ್",
                "ರಾಜುಗೆ ೬ ಕಿಲೋ ಅಕ್ಕಿ ಬೇಕು",
            ),
        )
        assert row.draft["partyId"] is None
        assert row.draft["partyName"] and "ರಾಜು" in row.draft["partyName"]


def test_html_only_mail_is_reduced_to_its_text(client, workspace, inbox_token):
    message = EmailMessage()
    message["From"] = "anita@example.com"
    message["To"] = f"orders+{inbox_token}@smartsme.local"
    message["Subject"] = "Order"
    message["Message-ID"] = f"<{uuid.uuid4().hex}@example.com>"
    # No plain-text part at all: some senders only ever produce HTML.
    message.set_content(
        "<html><body><style>p{color:red}</style>"
        "<p>Please send 3 Cooking Oil to Anita Stores</p></body></html>",
        subtype="html",
    )
    with SessionLocal() as db:
        row = _deliver(db, message.as_bytes())
        assert row.status == "pending"
        # Tags and the stylesheet are gone; the order survived.
        assert "<p>" not in row.body
        assert "color:red" not in row.body
        assert row.draft["items"][0]["quantity"] == 3


def test_mail_with_no_token_is_dropped(client, workspace):
    """An order addressed to nobody in particular must not land in someone's
    queue — guessing the business would be worse than losing the mail."""
    with SessionLocal() as db:
        assert _deliver(db, _raw_email("someone@smartsme.local", "Order", "3 Cooking Oil")) is None


def test_mail_with_an_unknown_token_is_dropped(client, workspace):
    with SessionLocal() as db:
        assert _deliver(db, _raw_email("orders+deadbeefdeadbeef@x.local", "Order", "3 oil")) is None


def test_the_same_email_is_never_ingested_twice(client, workspace, inbox_token):
    """Re-delivery, a restart mid-batch, or a POP3 server that forgets a DELE."""
    raw = _raw_email(f"orders+{inbox_token}@smartsme.local", "Order", "2 Cooking Oil")
    with SessionLocal() as db:
        assert _deliver(db, raw) is not None
        assert _deliver(db, raw) is None
        assert db.scalar(select(InboundMessage.id)) is not None
        assert len(list(db.scalars(select(InboundMessage)))) == 1


def test_an_unreadable_message_is_kept_rather_than_lost(client, workspace, inbox_token):
    """Someone wrote in; that is worth seeing even if nothing could be parsed."""
    with SessionLocal() as db:
        row = _deliver(db, _raw_email(f"orders+{inbox_token}@smartsme.local", "", "   "))
        assert row is not None
        assert row.status == "failed"
        assert row.note


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def _update(text: str, chat_id: int = 4242, message_id: int = 1) -> dict:
    return {
        "update_id": 100 + message_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": 7, "username": "anita", "first_name": "Anita"},
            "text": text,
        },
    }


def test_a_telegram_update_becomes_an_incoming_message():
    parsed = telegram_channel.to_incoming(_update("3 Cooking Oil please"))
    assert parsed is not None
    assert parsed.channel == "telegram"
    assert parsed.sender == "@anita"
    assert parsed.sender_name == "Anita"
    assert parsed.body == "3 Cooking Oil please"


def test_updates_without_text_are_ignored():
    assert telegram_channel.to_incoming({"update_id": 1, "message": {"chat": {"id": 1}}}) is None
    assert telegram_channel.to_incoming({"update_id": 2}) is None


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("/link abc123", "abc123"),
        ("/link  ABC123 ", "abc123"),
        ("/link@SmartSMEBot abc123", "abc123"),
        ("link abc123", "abc123"),
        ("3 bags rice", None),
        ("/link", None),
    ],
)
def test_the_link_command_is_recognised(text, token):
    assert telegram_channel.link_token_in(text) == token


def test_linking_a_chat_routes_its_later_messages(client, workspace, inbox_token, business_id):
    with SessionLocal() as db:
        _link_chat(db, "4242", inbox_token, "Anita")
        link = db.scalar(select(ChannelLink).where(ChannelLink.external_id == "4242"))
        assert link is not None
        assert link.business_id == business_id

        parsed = telegram_channel.to_incoming(_update("5 Cooking Oil for Anita Stores"))
        parsed.route_key = parsed.external_id
        parsed.external_id = "4242:1"
        row = ingest(db, parsed)
        assert row is not None
        assert row.business_id == business_id
        assert row.draft["items"][0]["quantity"] == 5


def test_an_unlinked_chat_is_dropped(client, workspace):
    with SessionLocal() as db:
        parsed = telegram_channel.to_incoming(_update("5 Cooking Oil", chat_id=9999))
        parsed.route_key = parsed.external_id
        parsed.external_id = "9999:1"
        assert ingest(db, parsed) is None


def test_two_messages_from_one_chat_both_arrive(client, workspace, inbox_token):
    """The dedup key is the message, not the chat — an easy thing to get wrong,
    and it would silently accept only the first order a customer ever sent."""
    with SessionLocal() as db:
        _link_chat(db, "4242", inbox_token, "Anita")
        for message_id in (1, 2):
            parsed = telegram_channel.to_incoming(
                _update(f"{message_id} Cooking Oil", message_id=message_id)
            )
            parsed.route_key = parsed.external_id
            parsed.external_id = f"4242:{message_id}"
            assert ingest(db, parsed) is not None
        assert len(list(db.scalars(select(InboundMessage)))) == 2


def test_linking_with_a_bad_token_creates_no_link(client, workspace, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(telegram_channel, "send_message", lambda chat, text: sent.append(text))
    with SessionLocal() as db:
        _link_chat(db, "5555", "not-a-real-token", None)
        assert db.scalar(select(ChannelLink).where(ChannelLink.external_id == "5555")) is None


# ---------------------------------------------------------------------------
# The queue, over HTTP
# ---------------------------------------------------------------------------
def test_the_queue_lists_what_arrived(client, workspace, inbox_token):
    with SessionLocal() as db:
        _deliver(
            db,
            _raw_email(
                f"orders+{inbox_token}@smartsme.local", "Order", "4 Cooking Oil to Anita Stores"
            ),
        )

    body = client.get("/api/inbox").json()
    assert body["pending"] == 1
    assert body["counts"]["pending"] == 1
    row = body["rows"][0]
    assert row["channel"] == "email"
    assert row["statusLabel"] == "Needs review"
    assert row["draft"]["items"][0]["quantity"] == 4


def test_accepting_records_a_real_sale(client, workspace, inbox_token):
    """The whole point of the feature, and the only path that writes."""
    with SessionLocal() as db:
        _deliver(
            db,
            _raw_email(
                f"orders+{inbox_token}@smartsme.local", "Order", "4 Cooking Oil to Anita Stores"
            ),
        )

    row = client.get("/api/inbox").json()["rows"][0]
    before = {p["id"]: p for p in client.get("/api/products").json()["rows"]}
    opening = before[workspace["productId"]]["stock"]

    draft = dict(row["draft"])
    draft["items"] = [
        {
            "productId": workspace["productId"],
            "description": "Cooking Oil",
            "quantity": 4,
            "unitPrice": 140,
        }
    ]
    accepted = client.post(f"/api/inbox/{row['id']}/accept", json=draft)
    assert accepted.status_code == 200, accepted.text

    after = {p["id"]: p for p in client.get("/api/products").json()["rows"]}
    assert after[workspace["productId"]]["stock"] == opening - 4

    listed = client.get("/api/inbox").json()
    assert listed["counts"]["accepted"] == 1
    assert listed["pending"] == 0
    assert listed["rows"][0]["handledAt"] is not None


def test_pending_count_is_what_the_badge_polls(client, employee_client, workspace, inbox_token):
    """The sidebar badge's one query: cheap, and visible to everyone signed in.

    Both the owner and the employee need it — an order belongs to the shop, not
    to whoever happened to be looking at the Inbox when it arrived.
    """
    assert client.get("/api/inbox/pending-count").json() == {"pending": 0}

    with SessionLocal() as db:
        _deliver(db, _raw_email(f"orders+{inbox_token}@smartsme.local", "Order", "1 Cooking Oil"))

    assert client.get("/api/inbox/pending-count").json() == {"pending": 1}
    assert employee_client.get("/api/inbox/pending-count").json() == {"pending": 1}

    # Dealing with it clears the badge rather than leaving a number nobody can
    # get rid of.
    row = client.get("/api/inbox").json()["rows"][0]
    assert client.post(f"/api/inbox/{row['id']}/reject").status_code == 200
    assert client.get("/api/inbox/pending-count").json() == {"pending": 0}


def test_the_recorded_source_names_the_channel(client, workspace, inbox_token):
    """An emailed order says "email", a Telegram order says "telegram".

    Everything inbound used to land as "nlp" — the same badge a typed note
    gets — so the ledger could not answer "where did this order come from?",
    which is the first thing anyone asks when a figure looks wrong.
    """
    with SessionLocal() as db:
        _deliver(db, _raw_email(f"orders+{inbox_token}@smartsme.local", "Order", "1 Cooking Oil"))
        _link_chat(db, "4242", inbox_token, "Anita")
        parsed = telegram_channel.to_incoming(_update("2 Cooking Oil"))
        parsed.route_key = parsed.external_id
        parsed.external_id = "4242:1"
        ingest(db, parsed)

    item = {
        "productId": workspace["productId"],
        "description": "Cooking Oil",
        "quantity": 1,
        "unitPrice": 140,
    }
    for row in client.get("/api/inbox").json()["rows"]:
        draft = dict(row["draft"])
        draft["items"] = [item]
        # A review screen that insisted on another source must not be believed.
        draft["source"] = "form"
        assert client.post(f"/api/inbox/{row['id']}/accept", json=draft).status_code == 200

    sources = {s["source"] for s in client.get("/api/sales").json()["rows"]}
    assert {"email", "telegram"} <= sources


def test_a_message_cannot_be_accepted_twice(client, workspace, inbox_token):
    with SessionLocal() as db:
        _deliver(db, _raw_email(f"orders+{inbox_token}@smartsme.local", "Order", "1 Cooking Oil"))
    row = client.get("/api/inbox").json()["rows"][0]
    draft = dict(row["draft"])
    draft["items"] = [
        {
            "productId": workspace["productId"],
            "description": "Cooking Oil",
            "quantity": 1,
            "unitPrice": 140,
        }
    ]
    assert client.post(f"/api/inbox/{row['id']}/accept", json=draft).status_code == 200
    assert client.post(f"/api/inbox/{row['id']}/accept", json=draft).status_code == 409


def test_rejecting_records_nothing(client, workspace, inbox_token):
    with SessionLocal() as db:
        _deliver(
            db, _raw_email(f"orders+{inbox_token}@smartsme.local", "Spam", "buy cheap watches")
        )
    row = client.get("/api/inbox").json()["rows"][0]
    sales_before = client.get("/api/sales").json()["page"]["total"]

    assert client.post(f"/api/inbox/{row['id']}/reject").status_code == 200
    assert client.get("/api/sales").json()["page"]["total"] == sales_before

    listed = client.get("/api/inbox").json()
    assert listed["counts"]["rejected"] == 1
    assert listed["pending"] == 0


def test_handled_messages_can_be_cleared(client, workspace, inbox_token):
    with SessionLocal() as db:
        _deliver(db, _raw_email(f"orders+{inbox_token}@smartsme.local", "A", "1 Cooking Oil"))
        _deliver(db, _raw_email(f"orders+{inbox_token}@smartsme.local", "B", "2 Cooking Oil"))

    rows = client.get("/api/inbox").json()["rows"]
    client.post(f"/api/inbox/{rows[0]['id']}/reject")

    cleared = client.post("/api/inbox/clear-handled")
    assert cleared.json()["removed"] == 1
    left = client.get("/api/inbox").json()
    assert left["pending"] == 1


def test_an_employee_can_work_the_queue_but_not_delete_from_it(
    client, employee_client, workspace, inbox_token
):
    with SessionLocal() as db:
        _deliver(db, _raw_email(f"orders+{inbox_token}@smartsme.local", "Order", "1 Cooking Oil"))

    row = employee_client.get("/api/inbox").json()["rows"][0]
    draft = dict(row["draft"])
    draft["items"] = [
        {
            "productId": workspace["productId"],
            "description": "Cooking Oil",
            "quantity": 1,
            "unitPrice": 140,
        }
    ]
    # Recording an order is exactly what an employee is for.
    assert employee_client.post(f"/api/inbox/{row['id']}/accept", json=draft).status_code == 200
    # Erasing the record of what arrived is not.
    assert employee_client.post("/api/inbox/clear-handled").status_code == 403
    assert employee_client.delete(f"/api/inbox/{row['id']}").status_code == 403


def test_the_queue_is_scoped_to_one_business(client, workspace, inbox_token, other_business_id):
    with SessionLocal() as db:
        other_token = db.scalar(
            select(Business.inbox_token).where(Business.id == uuid.UUID(other_business_id))
        )
        _deliver(db, _raw_email(f"orders+{other_token}@smartsme.local", "Order", "9 Cooking Oil"))

    # Delivered to the neighbour, so it must not show up here.
    assert client.get("/api/inbox").json()["pending"] == 0


def test_an_unknown_status_filter_is_rejected(client):
    assert client.get("/api/inbox", params={"status": "maybe"}).status_code == 400


def test_the_inbox_page_is_told_the_whole_address(client):
    """The page used to build the address itself, with the domain hard-coded in
    the frontend. The server owns that setting, so the server composes it."""
    from app.core.config import settings

    body = client.get("/api/inbox").json()
    assert body["inboxAddress"] == f"orders+{body['inboxToken']}@{settings.inbox_domain}"


def test_the_cli_prints_where_orders_arrive(capsys):
    """`python -m app.cli inbox-token` exists so nobody has to hunt for the
    token in the UI before they can send a test order."""
    from app.cli import main

    assert main(["inbox-token"]) == 0
    printed = capsys.readouterr().out
    assert "token" in printed and "orders+" in printed and "/link " in printed


# ---------------------------------------------------------------------------
# A photographed order sent to the bot
# ---------------------------------------------------------------------------
def _photo_update(file_id="AgACfile", with_caption=False, as_document=False):
    message = {"chat": {"id": "77"}, "from": {"username": "shopkeeper"}, "message_id": 9}
    if as_document:
        message["document"] = {"file_id": file_id, "mime_type": "image/png", "file_size": 2048}
    else:
        message["photo"] = [
            {"file_id": "small", "file_size": 800},
            {"file_id": file_id, "file_size": 2048},
        ]
    if with_caption:
        message["caption"] = "order from anita"
    return {"update_id": 500, "message": message}


def test_the_largest_photo_size_is_the_one_read(monkeypatch):
    """Telegram sends several recompressed sizes; a smaller one loses exactly
    the handwriting we are trying to read."""
    from app.inbound import telegram as tg

    chosen = tg.photo_in(_photo_update()["message"])
    assert chosen == ("AgACfile", "image/jpeg")


def test_a_file_send_is_preferred_over_a_recompressed_photo(monkeypatch):
    from app.inbound import telegram as tg

    message = _photo_update(as_document=True)["message"]
    message["photo"] = [{"file_id": "compressed", "file_size": 900}]
    assert tg.photo_in(message) == ("AgACfile", "image/png")


def test_an_oversized_photo_is_refused_rather_than_downloaded():
    from app.inbound import telegram as tg

    message = {"photo": [{"file_id": "huge", "file_size": tg.MAX_PHOTO_BYTES + 1}]}
    assert tg.photo_in(message) is None


def test_a_photo_becomes_an_incoming_message_carrying_the_image(monkeypatch):
    from app.inbound import telegram as tg

    monkeypatch.setattr(tg, "download", lambda _id: b"\x89PNG-pretend")
    parsed = tg.to_incoming(_photo_update())
    assert parsed is not None
    assert parsed.image == b"\x89PNG-pretend"
    assert parsed.image_media_type == "image/jpeg"


def test_a_photo_telegram_will_not_hand_over_is_dropped(monkeypatch):
    """Queuing a message whose picture never arrived is worse than not queuing
    it: the row would sit in the inbox with nothing in it to read."""
    from app.inbound import telegram as tg

    monkeypatch.setattr(tg, "download", lambda _id: None)
    assert tg.to_incoming(_photo_update()) is None
    # Unless there was a caption, which is still an order worth reading.
    assert tg.to_incoming(_photo_update(with_caption=True)) is not None


def test_a_photographed_order_is_read_by_the_image_path(
    client, workspace, inbox_token, monkeypatch
):
    """The picture goes through the same engines as a Smart Input upload."""
    from app import smart_input
    from app.ai.ocr import ParsedInvoice, ParsedInvoiceLine
    from app.inbound.pipeline import IncomingMessage, ingest

    monkeypatch.setattr(
        smart_input,
        "read_image",
        lambda *_a, **_k: (
            ParsedInvoice(
                party="Anita Stores",
                lineItems=[ParsedInvoiceLine(product="Cooking Oil", quantity=7)],
            ),
            "vision",
        ),
    )

    with SessionLocal() as db:
        row = ingest(
            db,
            IncomingMessage(
                channel="email",  # routed by token, exactly like a plus-addressed mail
                external_id=f"<{uuid.uuid4().hex}@photo>",
                sender="shopkeeper@example.com",
                body="",
                token=inbox_token,
                image=b"pretend-jpeg",
            ),
        )

    assert row is not None
    assert row.status == "pending"
    assert row.body == "(photographed order)", "a bare photo still needs a label in the list"
    assert row.draft["partyId"] == workspace["customerId"]
    assert row.draft["items"][0]["quantity"] == 7


def test_the_page_is_told_which_channels_are_actually_on(client, monkeypatch):
    """A switched-off channel and an empty mailbox look identical from outside.

    Mail sat in Mailpit, addressed correctly, while EMAIL_INGEST_ENABLED was
    false - so "Check now" answered `queued: 0`, exactly as it would have for a
    mailbox with nothing in it, and there was no way to tell the difference from
    the page. The status travels with the response so the page can say so.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "email_ingest_enabled", False)
    monkeypatch.setattr(settings, "telegram_bot_token", "")

    listing = client.get("/api/inbox").json()
    assert listing["channels"] == {"email": False, "telegram": False}

    swept = client.post("/api/inbox/collect").json()
    assert swept["channels"] == {"email": False, "telegram": False}
    assert swept["queued"] == 0

    monkeypatch.setattr(settings, "email_ingest_enabled", True)
    assert client.get("/api/inbox").json()["channels"]["email"] is True
