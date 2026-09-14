"""The event bus, stored as a transactional outbox.

Business rows and the event that describes them are committed in the same
transaction, so an event can never exist for a write that rolled back — and a
write can never be silently missed by the worker.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, count, fk, pk, timestamp


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    #: Who caused it. Null for events raised by the seed, by a cron drain, or by
    #: a user who has since been removed from the team.
    user_id: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: pending | processing | processed | failed
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    retry_count: Mapped[int] = count()
    error: Mapped[str | None] = mapped_column(Text)
    #: When a worker took this event. The sweep needs it to tell a worker that
    #: died from one that is merely slow; `created_at` cannot answer that,
    #: because the case the sweep exists for - a broker outage, then a backlog
    #: draining - is one where every event is old by definition.
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = timestamp()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
