"""Customers and suppliers."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, money, pk, timestamp


class Party(Base):
    """A customer or a supplier.

    A positive `balance` means they owe us (customer) or we owe them (supplier).
    """

    __tablename__ = "parties"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    type: Mapped[str] = mapped_column(Text, nullable=False)  # customer | supplier
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    gst_number: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    balance: Mapped[float] = money()
    created_at: Mapped[datetime] = timestamp()
