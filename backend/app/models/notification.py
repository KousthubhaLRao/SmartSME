"""In-app notifications raised by workflow actions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, fk, pk, timestamp


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    #: What raised it. Both nullable: an alert outlives the rule or event it
    #: came from rather than disappearing with it.
    event_id: Mapped[uuid.UUID | None] = fk("events.id", ondelete="SET NULL", nullable=True)
    rule_id: Mapped[uuid.UUID | None] = fk("workflow_rules.id", ondelete="SET NULL", nullable=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        Text, nullable=False, default="info", server_default="info"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = timestamp()
