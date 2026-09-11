"""The tenant root and the people who sign in to it."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, business_fk, money, pk, timestamp


class Business(Base):
    """One tenant. Every other table is scoped to a business."""

    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    gst_number: Mapped[str | None] = mapped_column(Text)
    pan_number: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR", server_default="INR")
    tax_rate: Mapped[float] = money(18)
    invoice_prefix: Mapped[str] = mapped_column(
        Text, nullable=False, default="INV", server_default="INV"
    )
    created_at: Mapped[datetime] = timestamp()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="owner", server_default="owner")
    created_at: Mapped[datetime] = timestamp()

    business: Mapped[Business] = relationship(lazy="joined")
