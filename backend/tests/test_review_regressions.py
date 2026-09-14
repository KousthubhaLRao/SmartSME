"""Regressions for bugs a pre-push review caught.

Each of these passed review by reading the code, not by failing a test — which
is the point of writing them down. Every one is a thing that was shipped-ready
and wrong.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from email.message import EmailMessage

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.inbound import email as email_channel
from app.inbound.pipeline import ingest
from app.models import Business, Event, InboundMessage


@pytest.fixture
def inbox_token(client) -> str:
    return client.get("/api/inbox").json()["inboxToken"]


@pytest.fixture(autouse=True)
def clean_queue():
    yield
    with SessionLocal() as db:
        db.query(InboundMessage).delete()
        db.commit()


def _deliver(db, to: str, subject: str, body: str):
    message = EmailMessage()
    message["From"] = "Supplier <supplier@example.com>"
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = f"<{uuid.uuid4().hex}@example.com>"
    message.set_content(body)
    parsed = email_channel.to_incoming(message.as_bytes(), fallback_id="regression")
    return ingest(db, parsed)


# ---------------------------------------------------------------------------
# 1. An emailed purchase was recorded as a sale
# ---------------------------------------------------------------------------
def test_an_emailed_purchase_is_recorded_as_a_purchase(client, workspace, inbox_token):
    """`publish_draft` read `payload["type"]`, but a draft names that field
    `suggestedType`, so every accepted message defaulted to a sale — an inbound
    purchase took stock *out* instead of putting it in."""
    with SessionLocal() as db:
        row = _deliver(
            db,
            f"orders+{inbox_token}@smartsme.local",
            "Delivery",
            "bought 10 Cooking Oil from ABC Suppliers",
        )
    assert row.draft["suggestedType"] == "purchase", "the parser should see a purchase"

    opening = {p["id"]: p for p in client.get("/api/products").json()["rows"]}[
        workspace["productId"]
    ]["stock"]

    queued = client.get("/api/inbox").json()["rows"][0]
    draft = dict(queued["draft"])
    draft["partyId"] = workspace["supplierId"]
    draft["items"] = [
        {
            "productId": workspace["productId"],
            "description": "Cooking Oil",
            "quantity": 10,
            "unitPrice": 100,
        }
    ]
    accepted = client.post(f"/api/inbox/{queued['id']}/accept", json=draft)
    assert accepted.status_code == 200, accepted.text

    after = {p["id"]: p for p in client.get("/api/products").json()["rows"]}[
        workspace["productId"]
    ]["stock"]
    assert after == opening + 10, "a purchase must add stock, not remove it"


def test_publish_draft_accepts_either_field_name(client, workspace):
    """The Smart Input form sends `type`; a draft carries `suggestedType`. Both
    have to mean the same thing."""
    from app.smart_input import publish_draft

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        result = publish_draft(
            db,
            business_id,
            {
                "suggestedType": "expense",
                "category": "Transport",
                "note": "Auto fare from the inbox",
                "amount": 90,
            },
        )
    assert "Expense" in result["ok"]
    # The note becomes the description when no explicit one is given.
    assert any(
        e["description"] == "Auto fare from the inbox"
        for e in client.get("/api/expenses").json()["rows"]
    )


# ---------------------------------------------------------------------------
# 2. Native-script names could never match the catalogue
# ---------------------------------------------------------------------------
def test_a_kannada_name_matches_a_kannada_catalogue_entry(client):
    """`_norm` stripped every non-ASCII character, so a Devanagari or Kannada
    name normalised to "" and matched nothing — the multilingual parser could
    read a name it could never resolve."""
    from app.smart_input import best_match

    class Row:
        def __init__(self, name):
            self.name = name

    kannada = [Row("ಅಕ್ಕಿ"), Row("ಸಕ್ಕರೆ")]
    assert best_match(kannada, "ಅಕ್ಕಿ") is kannada[0]

    hindi = [Row("चावल"), Row("चीनी")]
    assert best_match(hindi, "चावल") is hindi[0]

    # And English still behaves exactly as before.
    english = [Row("Anita Stores"), Row("Kumar Traders")]
    assert best_match(english, "anita") is english[0]
    assert best_match(english, "ANITA  STORES.") is english[0]
    assert best_match(english, "nobody") is None


def test_a_kannada_product_resolves_end_to_end(client, workspace):
    """The whole point of the feature: a Kannada note reaching a real product."""
    created = client.post(
        "/api/products",
        json={"name": "ಅಕ್ಕಿ", "unit": "kg", "sellingPrice": 60, "stock": 100},
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    draft = client.post("/api/input/parse-text", json={"text": "ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ"}).json()[
        "draft"
    ]

    assert draft["items"][0]["productId"] == product_id, "the Kannada product should resolve"
    assert draft["items"][0]["unitPrice"] == 60, "and bring its price with it"

    client.delete(f"/api/products/{product_id}")


# ---------------------------------------------------------------------------
# 3. Erasing alert history needed only read permission
# ---------------------------------------------------------------------------
def test_destroying_alerts_needs_more_than_read(client, employee_client, workspace):
    """An employee cannot delete a sale; deleting the record that a stock alert
    ever fired is the same kind of act."""
    from app.models import Notification

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        alert = Notification(
            business_id=business_id,
            type="workflow",
            severity="warning",
            title="Permission probe",
            message="Raised for a permission test.",
        )
        db.add(alert)
        db.commit()
        alert_id = alert.id

    assert employee_client.delete(f"/api/notifications/{alert_id}").status_code == 403
    assert employee_client.post("/api/notifications/clear-read").status_code == 403
    # The owner still can.
    assert client.delete(f"/api/notifications/{alert_id}").status_code == 200


# ---------------------------------------------------------------------------
# 4. Events abandoned by a dead worker were stranded forever
# ---------------------------------------------------------------------------
def test_the_sweep_releases_events_a_dead_worker_left_claimed(client, monkeypatch):
    """A worker killed mid-event leaves the row in `processing`. The sweep only
    looked at `pending`, and a redelivered task loses the claim race, so the
    event was never applied by anyone."""
    from app.core.config import settings
    from app.tasks import sweep_outbox

    monkeypatch.setattr(settings, "celery_stranded_seconds", 1.0)
    sent: list[str] = []
    monkeypatch.setattr("app.tasks.enqueue", lambda ids: sent.extend(str(i) for i in ids))

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        abandoned = Event(
            business_id=business_id,
            type="PAYMENT_RECEIVED",
            payload={"abandoned": True},
            status="processing",
            created_at=datetime.now() - timedelta(hours=2),
        )
        db.add(abandoned)
        db.commit()
        event_id = abandoned.id

    sweep_outbox()

    with SessionLocal() as db:
        revived = db.scalar(select(Event).where(Event.id == event_id))
        assert revived.status in ("pending", "done"), "it should have been released"
        db.delete(revived)
        db.commit()
    assert str(event_id) in sent, "and handed back to a worker"


def test_the_sweep_leaves_a_freshly_claimed_event_alone(client, monkeypatch):
    """A task that is merely *slow* must not have its event stolen mid-flight."""
    from app.tasks import sweep_outbox

    sent: list[str] = []
    monkeypatch.setattr("app.tasks.enqueue", lambda ids: sent.extend(str(i) for i in ids))

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        working = Event(
            business_id=business_id,
            type="PAYMENT_RECEIVED",
            payload={"in-flight": True},
            status="processing",
        )
        db.add(working)
        db.commit()
        event_id = working.id

    sweep_outbox()

    with SessionLocal() as db:
        still = db.scalar(select(Event).where(Event.id == event_id))
        assert still.status == "processing"
        db.delete(still)
        db.commit()
    assert str(event_id) not in sent


# ---------------------------------------------------------------------------
# 7. Two customers sharing a name were merged in the chart
# ---------------------------------------------------------------------------
def test_two_customers_with_the_same_name_stay_separate(client, workspace):
    """Grouping the top-customer breakdown by name merged distinct parties and
    overstated whoever they were merged into."""
    name = f"Sharma Stores {uuid.uuid4().hex[:4]}"
    ids = []
    for _ in range(2):
        created = client.post("/api/parties", json={"type": "customer", "name": name})
        assert created.status_code == 201
        ids.append(created.json()["id"])

    for party_id in ids:
        client.post(
            "/api/sales",
            json={
                "partyId": party_id,
                "items": [
                    {
                        "productId": workspace["productId"],
                        "description": "Cooking Oil",
                        "quantity": 1,
                        "unitPrice": 140,
                    }
                ],
                "amountPaid": 140,
            },
        )

    rows = client.get("/api/reports/overview").json()["topCustomers"]
    same_name = [r for r in rows if r["label"] == name]
    # Both appear in their own right rather than as one doubled entry.
    assert len(same_name) == 2, f"expected two separate rows, got {same_name}"

    for party_id in ids:
        client.delete(f"/api/parties/{party_id}")
