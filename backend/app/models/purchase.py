"""Purchases: the inbound document and its line items."""

from __future__ import annotations

import uuid

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, DocumentMixin, LineItemMixin, business_fk, fk, pk


class Purchase(Base, DocumentMixin):
    __tablename__ = "purchases"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    party_id: Mapped[uuid.UUID | None] = fk("parties.id", ondelete="SET NULL", nullable=True)
    reference_number: Mapped[str] = mapped_column(Text, nullable=False)

    items: Mapped[list[PurchaseItem]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan", lazy="selectin"
    )


class PurchaseItem(Base, LineItemMixin):
    __tablename__ = "purchase_items"

    id: Mapped[uuid.UUID] = pk()
    purchase_id: Mapped[uuid.UUID] = fk("purchases.id")
    product_id: Mapped[uuid.UUID | None] = fk("products.id", ondelete="SET NULL", nullable=True)

    purchase: Mapped[Purchase] = relationship(back_populates="items")
