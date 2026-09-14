"""The Celery application.

Redis is the broker only. The transactional outbox in Postgres stays the source
of truth — an event is committed in the same transaction as the business data it
describes, and Celery is the thing that gets told to go and apply it. That
ordering is what keeps the guarantee that an event can never exist for a write
that rolled back, and a write can never be silently missed:

    write + event  ──commit──►  Postgres (source of truth)
                                     │
                                     ├── enqueue ──► Redis ──► worker applies it
                                     │
                                     └── sweep ────────────────► worker applies it
                                         (anything the enqueue missed)

If Redis is down when the event is published, nothing is lost: the row is
already committed as `pending`, and the periodic sweep picks it up as soon as
the broker is back.

Run a worker with:

    celery -A app.celery_app worker --loglevel=info --pool=solo   # Windows
    celery -A app.celery_app worker --loglevel=info -c 8          # Linux

and the sweeper with:

    celery -A app.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from .core.config import settings

QUEUE = "smartsme"

celery_app = Celery(
    "smartsme",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue=QUEUE,
    # Acknowledge only after the task finishes, so a worker killed mid-event
    # returns it to the queue instead of dropping it.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Events are cheap and ordering matters more than batching, so hand out one
    # at a time rather than letting a worker hoard a prefetch buffer.
    worker_prefetch_multiplier=1,
    # A stuck event must not hold a worker forever.
    task_time_limit=120,
    task_soft_time_limit=90,
    result_expires=3600,
    beat_schedule={
        "sweep-outbox": {
            "task": "smartsme.sweep_outbox",
            "schedule": settings.celery_sweep_seconds,
            "options": {"queue": QUEUE, "expires": settings.celery_sweep_seconds * 2},
        },
        "collect-inbound": {
            "task": "smartsme.collect_inbound",
            "schedule": settings.inbound_poll_seconds,
            "options": {"queue": QUEUE, "expires": settings.inbound_poll_seconds * 2},
        },
    },
)
