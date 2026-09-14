"""Celery tasks: apply one event, and sweep the outbox for anything missed.

Both reuse the same claim-and-process functions the in-process worker uses, so
there is exactly one implementation of "what happens to an event" no matter
which dispatch mode is running.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update

from .celery_app import QUEUE, celery_app
from .core.config import settings
from .core.db import SessionLocal
from .models import Event
from .worker import claim, process_claimed

log = logging.getLogger("smartsme.tasks")


@celery_app.task(name="smartsme.process_event", bind=True, max_retries=0)
def process_event(self, event_id: str) -> str:
    """Apply one event.

    Retries are *not* Celery's job here: the outbox already tracks
    `retry_count` per event and dead-letters at the limit, and a failed event is
    put back to `pending` for the sweep to pick up. Letting Celery retry as well
    would double-count every failure.
    """
    eid = uuid.UUID(event_id)
    if not claim(eid):
        # Someone else got there first — an inline drain, another worker, or a
        # duplicate delivery. Not an error.
        return "skipped"

    # Applying an event can raise more of them: a sale chains STOCK_UPDATED,
    # which may chain a low-stock alert. Those are committed as pending inside
    # the worker's own transaction, where nothing has enqueued them, so the
    # chain is handed on here. Without this the follow-ups would sit until the
    # next sweep, and a stock alert would arrive half a minute late.
    started = datetime.now()
    process_claimed(eid)
    enqueue(_raised_since(started, exclude=eid))
    return "processed"


def _raised_since(moment: datetime, exclude: uuid.UUID) -> list[uuid.UUID]:
    """Events that appeared while this task was working."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Event.id).where(
                    Event.status == "pending",
                    Event.created_at >= moment,
                    Event.id != exclude,
                )
            )
        )


@celery_app.task(name="smartsme.sweep_outbox")
def sweep_outbox() -> int:
    """Re-enqueue events that never reached a worker.

    This is what makes losing the broker survivable. It deliberately looks only
    at rows that have been sitting for a while, so it never races with an
    enqueue that is already in flight.
    """
    now = datetime.now()
    cutoff = now - timedelta(seconds=settings.celery_stranded_seconds)
    # A worker that died mid-event leaves the row claimed as `processing`, where
    # nothing would ever look at it again: the sweep only reads `pending`, and a
    # redelivered task loses the claim race and reports "skipped". Anything held
    # far longer than a task could legitimately take is released back first.
    #
    # The age that matters is the age of the *claim*, not of the event. Judging
    # by `created_at` gets it exactly backwards in the situation this sweep is
    # for: after a broker outage the backlog is all old, so every row a live
    # worker had just picked up looked abandoned, and the sweep handed it to a
    # second worker - two workers running one event's rules side by side, which
    # is the duplicate notification that outbox processing exists to prevent.
    abandoned = now - timedelta(seconds=max(settings.celery_stranded_seconds * 10, 300))
    with SessionLocal() as db:
        released = db.execute(
            update(Event)
            .where(
                Event.status == "processing",
                # coalesce: rows claimed before this column existed have no
                # claim time, and falling back to `created_at` is right for
                # them - they genuinely are strays from an older process.
                func.coalesce(Event.claimed_at, Event.created_at) <= abandoned,
            )
            .values(status="pending", claimed_at=None)
        ).rowcount
        if released:
            db.commit()
            log.warning("released %s event(s) abandoned by a dead worker", released)
        else:
            db.rollback()

        stranded = list(
            db.scalars(
                select(Event.id)
                .where(Event.status == "pending", Event.created_at <= cutoff)
                .order_by(Event.created_at.asc())
                .limit(500)
            )
        )

    # Through the same hand-off the writes use, so a broker that is still down
    # is logged rather than crashing the beat schedule.
    sent = enqueue(stranded)
    if sent:
        log.info("swept %s stranded event(s) back onto the queue", sent)
    return sent


@celery_app.task(name="smartsme.collect_inbound")
def collect_inbound() -> dict:
    """Sweep the inbound channels. Scheduled by beat in celery mode; the
    in-process worker does the same job in inline mode."""
    from .inbound.collector import collect

    with SessionLocal() as db:
        collected = collect(db)
    if any(collected.values()):
        log.info("collected inbound: %s", collected)
    return collected


def enqueue(event_ids: list[uuid.UUID]) -> int:
    """Hand events to Redis. Never raises: a broker that is down must not fail
    the HTTP request that just committed the write, because the sweep will
    deliver the event once Redis is back."""
    sent = 0
    for event_id in event_ids:
        try:
            process_event.apply_async(args=[str(event_id)], queue=QUEUE)
            sent += 1
        except Exception:
            log.exception("could not enqueue event %s; the sweep will retry it", event_id)
    return sent
