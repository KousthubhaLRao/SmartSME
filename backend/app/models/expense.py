"""Standalone business expenses (not tied to a purchase document)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, money, pk, timestamp


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    category: Mapped[str] = mapped_column(
        Text, nullable=False, default="General", server_default="General"
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float] = money()
    #: Set by a workflow rule, e.g. "High-value expense, needs review".
    flagged: Mapped[str | None] = mapped_column(Text)
    date: Mapped[datetime] = timestamp()
    created_at: Mapped[datetime] = timestamp()
