"""Event dispatch: inline and Celery.

The contract these protect is that *both* modes apply exactly the same effects,
because they share one implementation of what happens to an event. Inline is the
default and is what every other test in the suite exercises; here the Celery path
is driven directly, with the broker faked, so the whole thing runs offline.

One test at the bottom talks to a real Redis and skips when there is not one.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Business, Event, Product

#: A type with no core effect, so a fabricated event exercises the plumbing
#: without needing a real document behind it.
INERT = "PAYMENT_RECEIVED"


@pytest.fixture(autouse=True)
def no_leftovers():
    """Fabricated events must not outlive their test: a later test that drains
    the queue would otherwise pick them up."""
    yield
    with SessionLocal() as db:
        db.query(Event).filter(Event.type == INERT).delete(synchronize_session=False)
        db.commit()


@pytest.fixture
def celery_mode(monkeypatch):
    """Switch dispatch to Celery for one test."""
    monkeypatch.setattr(settings, "event_dispatch", "celery")
    return settings


@pytest.fixture
def captured_enqueue(monkeypatch):
    """Replace the broker hand-off with a list, so no Redis is needed."""
    sent: list[str] = []

    def fake(event_ids):
        sent.extend(str(e) for e in event_ids)
        return len(event_ids)

    monkeypatch.setattr("app.tasks.enqueue", fake)
    return sent


def _stock(product_id) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Product.stock).where(Product.id == product_id))


def _pending() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(Event.id)).where(Event.status == "pending")) or 0


# ---------------------------------------------------------------------------
# Inline: the default, unchanged
# ---------------------------------------------------------------------------
def test_inline_applies_effects_before_the_write_returns(client, workspace):
    """The behaviour the SPA depends on, and the reason inline is the default."""
    assert settings.event_dispatch == "inline"
    before = _stock(uuid.UUID(workspace["productId"]))

    r = client.post(
        "/api/sales",
        json={
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 2,
                    "unitPrice": 140,
                }
            ],
            "amountPaid": 280,
        },
    )
    assert r.status_code == 201
    # No waiting, no polling: it is already done.
    assert _stock(uuid.UUID(workspace["productId"])) == before - 2


# ---------------------------------------------------------------------------
# Celery: hands off instead of doing the work
# ---------------------------------------------------------------------------
def test_celery_mode_enqueues_rather_than_processing(
    client, workspace, celery_mode, captured_enqueue
):
    before = _stock(uuid.UUID(workspace["productId"]))

    r = client.post(
        "/api/sales",
        json={
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
    assert r.status_code == 201

    # The row is committed and queued, but nothing has applied it yet.
    assert captured_enqueue, "the write should have handed its event to the broker"
    assert _stock(uuid.UUID(workspace["productId"])) == before, "effects must not be inline here"
    assert _pending() >= 1


def test_the_task_applies_the_event_and_passes_the_chain_on(client, workspace, captured_enqueue):
    """A sale chains STOCK_UPDATED from inside the worker, where nothing has
    enqueued it — the task has to hand the follow-up on itself."""
    from app.tasks import process_event

    before = _stock(uuid.UUID(workspace["productId"]))
    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))

    from app.domain.sales import create_sale
    from app.schemas import LineInput, SaleInput

    with SessionLocal() as db:
        sale = create_sale(
            db,
            business_id,
            SaleInput(
                items=[
                    LineInput(
                        productId=workspace["productId"],
                        description="Cooking Oil",
                        quantity=2,
                        unitPrice=140,
                    )
                ],
                amountPaid=280,
            ),
        )
    with SessionLocal() as db:
        event_id = db.scalar(
            select(Event.id).where(
                Event.type == "SALE_CREATED",
                Event.payload["saleId"].astext == str(sale.id),
            )
        )
    assert event_id is not None

    assert process_event(str(event_id)) == "processed"
    assert _stock(uuid.UUID(workspace["productId"])) == before - 2
    # The chained STOCK_UPDATED was handed to the broker rather than stranded.
    assert captured_enqueue, "the chained event should have been enqueued"


def test_an_event_is_only_ever_applied_once(client, workspace):
    """Redis can deliver a task twice; the claim has to make that harmless."""
    from app.tasks import process_event
    from app.worker import claim

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        event = Event(
            business_id=business_id, type=INERT, payload={"probe": True}, status="pending"
        )
        db.add(event)
        db.commit()
        event_id = event.id

    assert claim(event_id) is True
    # A second delivery finds it already taken and does nothing.
    assert process_event(str(event_id)) == "skipped"


def test_the_sweep_rescues_events_the_broker_never_got(client, captured_enqueue, monkeypatch):
    """If Redis was down at publish time the row is still committed, so the
    sweep is what eventually delivers it."""
    from app.tasks import sweep_outbox

    monkeypatch.setattr(settings, "celery_stranded_seconds", 1.0)
    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        stranded = Event(
            business_id=business_id,
            type=INERT,
            payload={"stranded": True},
            status="pending",
            # Old enough to count as abandoned.
            created_at=datetime.now() - timedelta(minutes=5),
        )
        db.add(stranded)
        db.commit()
        stranded_id = str(stranded.id)

    swept = sweep_outbox()
    assert swept >= 1
    assert stranded_id in captured_enqueue


def test_the_sweep_leaves_fresh_events_alone(client, captured_enqueue):
    """An event published a moment ago has an enqueue in flight; sweeping it
    would only duplicate the delivery."""
    from app.tasks import sweep_outbox

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        fresh = Event(
            business_id=business_id, type=INERT, payload={"fresh": True}, status="pending"
        )
        db.add(fresh)
        db.commit()
        fresh_id = str(fresh.id)

    sweep_outbox()
    assert fresh_id not in captured_enqueue


def test_a_broker_that_is_down_does_not_break_the_write(
    client,
    workspace,
    celery_mode,
    monkeypatch,
):
    """The event is already committed; failing the request would be worse than
    letting the sweep deliver it late."""
    from app import tasks

    def explode(*_args, **_kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(tasks.process_event, "apply_async", explode)

    r = client.post("/api/expenses", json={"description": "Broker down", "amount": 75})
    assert r.status_code == 201, r.text
    # Recorded and waiting, rather than lost.
    assert _pending() >= 1


# ---------------------------------------------------------------------------
# The real broker
# ---------------------------------------------------------------------------
def test_redis_round_trip():
    """Skipped unless a broker is actually running."""
    redis = pytest.importorskip("redis")
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        client.ping()
    except Exception:
        pytest.skip(f"no Redis at {settings.redis_url}")

    from app.celery_app import celery_app

    assert "smartsme.process_event" in celery_app.tasks
    assert "smartsme.sweep_outbox" in celery_app.tasks
    # The queue Celery would publish to is the one the workers are told to read.
    assert celery_app.conf.task_default_queue == "smartsme"
