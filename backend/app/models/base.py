"""Declarative base and the column helpers every model reuses.

Money is `double precision` and every amount passes through `round2` in the
domain layer. Timestamps are naive and treated as local time, so day and month
boundaries in reports line up with the user's calendar.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models; carries the shared metadata."""


def pk() -> Mapped[uuid.UUID]:
    """A UUID primary key, generated client-side so inserts need no round-trip."""
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk(target: str, *, ondelete: str = "CASCADE", nullable: bool = False) -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def business_fk() -> Mapped[uuid.UUID]:
    """Every tenant-scoped row points back at its business."""
    return fk("businesses.id")


def timestamp() -> Mapped[datetime]:
    return mapped_column(DateTime, nullable=False, server_default=func.now(), default=datetime.now)


def money(default: float = 0) -> Mapped[float]:
    return mapped_column(Float, nullable=False, default=default, server_default=str(default))


def count(default: int = 0) -> Mapped[int]:
    return mapped_column(Integer, nullable=False, default=default, server_default=str(default))


class DocumentMixin:
    """Columns shared by sales and purchases.

    Both are the same financial document in opposite directions, so the money
    columns, the discount triplet, the payment state and the back-datable
    business `date` live here instead of being duplicated.
    """

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="completed", server_default="completed"
    )
    subtotal: Mapped[float] = money()
    discount_type: Mapped[str] = mapped_column(
        Text, nullable=False, default="none", server_default="none"
    )
    discount_value: Mapped[float] = money()
    discount_amount: Mapped[float] = money()
    tax: Mapped[float] = money()
    total: Mapped[float] = money()
    amount_paid: Mapped[float] = money()
    payment_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="unpaid", server_default="unpaid"
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, default="form", server_default="form")
    notes: Mapped[str | None] = mapped_column(Text)
    #: Business date of the transaction (back-datable).
    date: Mapped[datetime] = timestamp()
    #: When the row was written, which is not necessarily the business date.
    created_at: Mapped[datetime] = timestamp()


class LineItemMixin:
    """Columns shared by sale_items and purchase_items."""

    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = count(1)
    unit_price: Mapped[float] = money()
    line_total: Mapped[float] = money()
