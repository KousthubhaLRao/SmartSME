"""Event worker.

Claims pending events one at a time (`status='pending' -> 'processing'`), runs
their workflow rules inside a single transaction, then marks them done, or
retries with a bounded counter and dead-letters after MAX_RETRIES.

`drain_queue` is the one entry point callers use. What it does depends on
EVENT_DISPATCH: in "inline" mode it runs the whole chain synchronously right
after a business write, so effects apply within the request; in "celery" mode it
hands the pending events to Redis and returns. The background thread is a
convenience for long-running hosts in inline mode; it is skipped when
DISABLE_WORKER is set, and in celery mode, where Celery owns the work.

The claim/process functions are public because the Celery tasks reuse them —
there is exactly one implementation of what happens to an event.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime

from sqlalchemy import select, update

from .core.config import settings
from .core.db import SessionLocal
from .models import Event
from .workflow import run_workflow_rules

log = logging.getLogger("smartsme.worker")

MAX_RETRIES = 5
BATCH = 20

_thread: threading.Thread | None = None
_inbound_thread: threading.Thread | None = None
_stop = threading.Event()
_tick_lock = threading.Lock()


def claim(event_id: uuid.UUID) -> bool:
    """Atomically take ownership of an event; False if someone else got it.

    The claim is timestamped, which is what lets the sweep distinguish an event
    a dead worker abandoned from one a live worker is still chewing on.
    """
    with SessionLocal() as db:
        claimed = db.execute(
            update(Event)
            .where(Event.id == event_id, Event.status == "pending")
            .values(status="processing", claimed_at=datetime.now())
            .returning(Event.id)
        ).scalar()
        db.commit()
        return claimed is not None


def process_claimed(event_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        try:
            event = db.scalar(select(Event).where(Event.id == event_id))
            if event is None:
                return
            run_workflow_rules(db, event)
            event.status = "done"
            event.processed_at = datetime.now()
            event.error = None
            db.commit()
        except Exception as err:
            db.rollback()
            _mark_failed(event_id, err)


def _mark_failed(event_id: uuid.UUID, err: Exception) -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.id == event_id))
        if event is None:
            return
        nxt = event.retry_count + 1
        event.retry_count = nxt
        event.status = "dead" if nxt >= MAX_RETRIES else "pending"
        event.error = str(err)[:2000]
        db.commit()
    log.warning("event %s failed (attempt %s): %s", event_id, nxt, err, exc_info=False)


def process_batch() -> int:
    """Process up to BATCH pending events. Returns how many were claimed."""
    with SessionLocal() as db:
        pending = list(
            db.scalars(
                select(Event.id)
                .where(Event.status == "pending")
                .order_by(Event.created_at.asc())
                .limit(BATCH)
            )
        )

    processed = 0
    for event_id in pending:
        if not claim(event_id):
            continue
        processed += 1
        process_claimed(event_id)
    return processed


def pending_ids(limit: int = BATCH) -> list[uuid.UUID]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Event.id)
                .where(Event.status == "pending")
                .order_by(Event.created_at.asc())
                .limit(limit)
            )
        )


def drain_queue(max_rounds: int = 12) -> int:
    """Deal with everything pending, the way this deployment is configured.

    In "inline" mode the chain is followed here and now, so a write's effects
    are applied before the request returns — a sale emits STOCK_UPDATED, which
    may raise a low-stock alert, and all of it lands before the client sees the
    201. In "celery" mode the events are handed to Redis instead and the request
    returns immediately; a worker applies them a moment later.

    Callers do not need to know which is in force.
    """
    if settings.event_dispatch == "celery":
        # Imported here: app.tasks imports this module.
        from .tasks import enqueue

        return enqueue(pending_ids(limit=BATCH * max_rounds))

    total = 0
    for _ in range(max_rounds):
        n = process_batch()
        total += n
        if n == 0:
            break
    return total


def tick() -> None:
    if not _tick_lock.acquire(blocking=False):
        return
    try:
        process_batch()
    finally:
        _tick_lock.release()


def _sweep_inbound() -> None:
    """Collect orders that arrived by email or Telegram. Imported here because
    the inbound package imports the domain layer, which imports this module."""
    from .core.db import SessionLocal as _Session
    from .inbound.collector import collect

    with _Session() as db:
        collected = collect(db)
    total = sum(collected.values())
    if total:
        log.info("collected %s inbound message(s): %s", total, collected)


def _run() -> None:
    log.info("SmartSME event worker running (polling every %ss)", settings.worker_poll_seconds)
    while not _stop.wait(settings.worker_poll_seconds):
        try:
            tick()
        except Exception:
            log.exception("worker tick failed")


def _run_inbound() -> None:
    """The inbound sweep, on its own thread and its own slower clock.

    Its own thread because it is both the slow one and the unreliable one: it
    talks to a mail server and then to an AI provider, either of which can sit
    there for a minute per message. Sharing a thread with `tick()` meant a
    mailbox nobody could reach also stopped sales from updating stock - a
    failure in an optional feature taking out the central one.
    """
    while not _stop.wait(settings.inbound_poll_seconds):
        try:
            _sweep_inbound()
        except Exception:
            log.exception("inbound sweep failed")


def start_worker() -> None:
    """The in-process pollers. Not started in celery mode, where a Celery worker
    does the work and Celery beat does the sweeping."""
    global _thread, _inbound_thread
    if settings.disable_worker or settings.event_dispatch == "celery" or _thread is not None:
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="smartsme-worker", daemon=True)
    _thread.start()
    _inbound_thread = threading.Thread(target=_run_inbound, name="smartsme-inbound", daemon=True)
    _inbound_thread.start()


def stop_worker() -> None:
    global _thread, _inbound_thread
    _stop.set()
    for thread in (_thread, _inbound_thread):
        if thread is not None:
            thread.join(timeout=5)
    _thread = None
    _inbound_thread = None
