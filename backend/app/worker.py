"""Event worker.

Claims pending events one at a time (`status='pending' -> 'processing'`), runs
their workflow rules inside a single transaction, then marks them done, or
retries with a bounded counter and dead-letters after MAX_RETRIES.

`drain_queue` runs the whole chain synchronously right after a business write,
so effects apply within the request. The background thread is a convenience for
long-running hosts; it is skipped when DISABLE_WORKER is set.
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
_stop = threading.Event()
_tick_lock = threading.Lock()


def _claim(event_id: uuid.UUID) -> bool:
    """Atomically take ownership of an event; False if someone else got it."""
    with SessionLocal() as db:
        claimed = db.execute(
            update(Event)
            .where(Event.id == event_id, Event.status == "pending")
            .values(status="processing")
            .returning(Event.id)
        ).scalar()
        db.commit()
        return claimed is not None


def _process_one(event_id: uuid.UUID) -> None:
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
    log.warning("event %s failed (attempt %s): %s", event_id, err, exc_info=False)


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
        if not _claim(event_id):
            continue
        processed += 1
        _process_one(event_id)
    return processed


def drain_queue(max_rounds: int = 12) -> int:
    """Drain the queue, following event chains (a sale emits STOCK_UPDATED,
    which may raise alerts) until nothing is left."""
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


def _run() -> None:
    log.info("SmartSME event worker running (polling every %ss)", settings.worker_poll_seconds)
    while not _stop.wait(settings.worker_poll_seconds):
        try:
            tick()
        except Exception:
            log.exception("worker tick failed")


def start_worker() -> None:
    global _thread
    if settings.disable_worker or _thread is not None:
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="smartsme-worker", daemon=True)
    _thread.start()


def stop_worker() -> None:
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)
        _thread = None
