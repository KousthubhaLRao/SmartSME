"""Regressions for the second pre-push review.

Six more, none overlapping the first pass. The first item here is the worst
kind: a fix from the first review that was wrong in its own way, so the test
that was meant to pin it down passed while the behaviour got less safe. Every
test below fails against the code as it stood before this round.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Business, Event, InboundMessage


@pytest.fixture(autouse=True)
def clean_queue():
    yield
    with SessionLocal() as db:
        db.query(InboundMessage).delete()
        db.commit()


def _business_id(db) -> uuid.UUID:
    return db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))


# ---------------------------------------------------------------------------
# 1. The sweep stole events from workers that were still running
# ---------------------------------------------------------------------------
def test_the_sweep_leaves_an_old_event_a_worker_just_claimed(client, monkeypatch):
    """The exact situation the sweep exists for: the broker was down, a backlog
    built up, and now it is draining. Every event in it is old, so judging by
    `created_at` said "abandoned" about rows a live worker had claimed seconds
    ago - and handed them to a second worker, which ran the same workflow rules
    again. It is the age of the *claim* that means anything.
    """
    from app.tasks import sweep_outbox
    from app.worker import claim

    sent: list[str] = []
    monkeypatch.setattr("app.tasks.enqueue", lambda ids: sent.extend(str(i) for i in ids))

    with SessionLocal() as db:
        backlogged = Event(
            business_id=_business_id(db),
            type="PAYMENT_RECEIVED",
            payload={"backlog": True},
            status="pending",
            created_at=datetime.now() - timedelta(hours=6),
        )
        db.add(backlogged)
        db.commit()
        event_id = backlogged.id

    # A worker picks it up, and is still working when the sweep runs.
    assert claim(event_id) is True
    sweep_outbox()

    with SessionLocal() as db:
        row = db.scalar(select(Event).where(Event.id == event_id))
        status, claimed_at = row.status, row.claimed_at
        db.delete(row)
        db.commit()

    assert status == "processing", "the sweep took an event out from under a live worker"
    assert str(event_id) not in sent, "and handed it to a second one"
    assert claimed_at is not None, "claiming an event must record when"


def test_the_sweep_still_frees_an_event_whose_worker_died(client, monkeypatch):
    """The other half: a claim old enough that no task could still be running.'"""
    from app.core.config import settings
    from app.tasks import sweep_outbox

    monkeypatch.setattr(settings, "celery_stranded_seconds", 1.0)
    sent: list[str] = []
    monkeypatch.setattr("app.tasks.enqueue", lambda ids: sent.extend(str(i) for i in ids))

    long_ago = datetime.now() - timedelta(hours=2)
    with SessionLocal() as db:
        abandoned = Event(
            business_id=_business_id(db),
            type="PAYMENT_RECEIVED",
            payload={"abandoned": True},
            status="processing",
            created_at=long_ago,
            claimed_at=long_ago,
        )
        db.add(abandoned)
        db.commit()
        event_id = abandoned.id

    sweep_outbox()

    with SessionLocal() as db:
        row = db.scalar(select(Event).where(Event.id == event_id))
        status = row.status
        db.delete(row)
        db.commit()
    assert status in ("pending", "done")
    assert str(event_id) in sent


# ---------------------------------------------------------------------------
# 2. A name with "and" in it was cut in half, then matched to someone else
# ---------------------------------------------------------------------------
def test_a_name_containing_and_survives_parsing():
    """ "and" was treated as a word that ends a name, so "Ram and Sons" arrived
    as "Ram" - and "Ram" then matched a different customer called Ramesh."""
    from app.ai.nlp import heuristic_parse

    assert heuristic_parse("sold 2 boxes to Ram and Sons for 1200").party == "Ram and Sons"
    assert heuristic_parse("bought 5 bags from Gupta and Company").party == "Gupta and Company"
    assert heuristic_parse("sold 2 kg salt and pepper to Anita Stores").product == "Salt and Pepper"


def test_a_short_name_does_not_match_a_longer_one():
    """Substring matching is the kind of wrong that only shows up on real data:
    every example anyone reaches for ("Anita" -> "Anita Stores") is a whole-word
    match, and the letters-inside-a-word cases are all mistakes."""
    from app.smart_input import best_match

    class Row:
        def __init__(self, name):
            self.name = name

    parties = [Row("Ramesh"), Row("Ram and Sons")]
    assert best_match(parties, "Ram and Sons") is parties[1]
    assert best_match(parties, "Ram") is parties[1], "Ram is not Ramesh"
    assert best_match(parties, "Ramesh") is parties[0]

    # What the loose matching was there for still works.
    stores = [Row("Anita Stores")]
    assert best_match(stores, "Anita") is stores[0]
    assert best_match(stores, "anita stores.") is stores[0]
    # Including the plural a catalogue and a note disagree about.
    assert best_match([Row("Biscuits")], "biscuit") is not None
    # And a name that shares no whole word matches nothing.
    assert best_match([Row("Kumar Traders")], "Kum") is None


def test_the_wrong_customer_is_not_billed(client, workspace):
    """End to end, because that is where it would have cost real money."""
    ramesh = client.post("/api/parties", json={"type": "customer", "name": "Ramesh"})
    ram = client.post("/api/parties", json={"type": "customer", "name": "Ram and Sons"})
    assert ramesh.status_code == 201 and ram.status_code == 201

    draft = client.post(
        "/api/input/parse-text", json={"text": "sold 2 Cooking Oil to Ram and Sons"}
    ).json()["draft"]
    assert draft["partyId"] == ram.json()["id"], f"billed to {draft['partyName']}"

    client.delete(f"/api/parties/{ramesh.json()['id']}")
    client.delete(f"/api/parties/{ram.json()['id']}")


# ---------------------------------------------------------------------------
# 3. Two-word names in Devanagari and Kannada lost their first word
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "note,party,product",
    [
        # Devanagari: "sold 5 kilos of rice to Anita Stores"
        ("अनीता स्टोर्स को 5 किलो चावल बेचा", "अनीता स्टोर्स", "चावल"),
        # Kannada, the same sentence
        ("ಅನಿತಾ ಸ್ಟೋರ್ಸ್ ಗೆ 5 ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ", "ಅನಿತಾ ಸ್ಟೋರ್ಸ್", "ಅಕ್ಕಿ"),
        # Romanised and lowercase, which had the same problem
        ("kumar traders ko 3 packet biscuit becha", "Kumar Traders", "Biscuit"),
    ],
)
def test_a_two_word_name_survives_in_every_script(note, party, product):
    """Whether the first word belonged to the name was decided by asking if it
    was capitalised - a question Devanagari and Kannada cannot answer, so the
    answer was always no and the first word was always thrown away."""
    from app.ai.nlp import heuristic_parse

    parsed = heuristic_parse(note)
    assert parsed.party == party, note
    assert parsed.product == product, note


@pytest.mark.parametrize(
    "note,party,product",
    [
        ("5 किलो चावल अनीता को बेचा", "अनीता", "चावल"),
        ("2 packet biscuit anita ko becha", "Anita", "Biscuit"),
    ],
)
def test_the_object_is_still_not_read_as_part_of_the_name(note, party, product):
    """The other word order, which is what the capitalisation test was for: the
    word after a quantity is what was sold, not who it went to."""
    from app.ai.nlp import heuristic_parse

    parsed = heuristic_parse(note)
    assert parsed.party == party, note
    assert parsed.product == product, note


# ---------------------------------------------------------------------------
# 4. An admin could dismiss and collect a tenant's inbound orders
# ---------------------------------------------------------------------------
def test_an_admin_cannot_dismiss_a_tenants_order(client, admin_client, business_id):
    """Rejecting decides the fate of a customer's order. Admin configures a
    business; it does not get to decide what happens to its orders."""
    with SessionLocal() as db:
        row = InboundMessage(
            business_id=uuid.UUID(business_id),
            channel="email",
            external_id=f"<perm-{uuid.uuid4().hex}@example.com>",
            sender="supplier@example.com",
            subject="Order",
            body="send 5 bags rice",
            status="pending",
            draft={"suggestedType": "sale", "items": []},
        )
        db.add(row)
        db.commit()
        message_id = row.id

    q = {"businessId": business_id}
    assert admin_client.get("/api/inbox", params=q).status_code == 200, "reading is allowed"
    assert admin_client.post(f"/api/inbox/{message_id}/reject", params=q).status_code == 403
    assert admin_client.post("/api/inbox/collect", params=q).status_code == 403

    # The owner can do both, and the employee who works the queue can too.
    assert client.post(f"/api/inbox/{message_id}/reject").status_code == 200


def test_collect_reports_this_businesss_own_queue(client):
    """It used to return the counts for every tenant on the server."""
    body = client.post("/api/inbox/collect").json()
    assert set(body) == {"checked", "queued", "pending"}
    assert body["queued"] == 0 and body["pending"] == 0


# ---------------------------------------------------------------------------
# 5. An unreadable Telegram update was re-fetched forever
# ---------------------------------------------------------------------------
def test_an_unreadable_update_is_still_acknowledged(monkeypatch):
    """A photo or a sticker parses to nothing. Skipping the acknowledgement
    meant Telegram handed it back every thirty seconds for a day, along with
    everything that arrived after it."""
    from app.inbound import collector
    from app.inbound import telegram as telegram_channel

    monkeypatch.setattr(collector, "_telegram_offset", None, raising=False)
    monkeypatch.setattr(telegram_channel, "enabled", lambda: True)

    calls: list[int | None] = []
    photo = {"update_id": 41, "message": {"chat": {"id": "7"}, "photo": [{"file_id": "x"}]}}

    def fake_get_updates(offset=None):
        calls.append(offset)
        return [photo] if len(calls) == 1 else []

    monkeypatch.setattr(telegram_channel, "get_updates", fake_get_updates)

    with SessionLocal() as db:
        assert collector._collect_telegram(db) == 0
        assert collector._collect_telegram(db) == 0

    assert calls == [None, 42], f"the offset never moved past the photo: {calls}"


# ---------------------------------------------------------------------------
# 6. A failing AI provider was retried for every single message
# ---------------------------------------------------------------------------
def test_a_failing_provider_is_dropped_rather_than_retried(monkeypatch):
    """At a 60-second timeout each, a batch of 25 mailed orders took 25 minutes
    to fail - and until recently it did that on the thread that applies events,
    so nothing else happened either."""
    from app.ai import client as ai_client

    ai_client.reset_breaker()
    attempts = {"n": 0}

    def always_fails(*args, **kwargs):
        attempts["n"] += 1
        raise TimeoutError("provider is not answering")

    monkeypatch.setattr(ai_client, "_openai_complete", always_fails)
    provider = ai_client.AiProvider(id="openai", label="Test", model="m", vision=False, api_key="k")

    failures = 0
    for _ in range(10):
        try:
            provider.complete(prompt="anything")
        except Exception:
            failures += 1

    assert failures == 10, "every call still fails"
    assert attempts["n"] == 3, f"the provider was called {attempts['n']} times, not 3"

    # A working provider clears it again.
    ai_client.reset_breaker()
    monkeypatch.setattr(ai_client, "_openai_complete", lambda *a, **k: "{}")
    assert provider.complete(prompt="anything") == "{}"


def test_the_inbound_sweep_runs_on_its_own_thread():
    """A mailbox nobody can reach must not stop sales from updating stock."""
    import inspect

    from app import worker

    assert "_sweep_inbound" not in inspect.getsource(worker._run)
    assert "_sweep_inbound" in inspect.getsource(worker._run_inbound)
