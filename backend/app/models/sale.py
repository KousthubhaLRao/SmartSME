"""Sales: the outbound document and its line items."""

from __future__ import annotations

import uuid

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, DocumentMixin, LineItemMixin, business_fk, fk, pk


class Sale(Base, DocumentMixin):
    __tablename__ = "sales"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    party_id: Mapped[uuid.UUID | None] = fk("parties.id", ondelete="SET NULL", nullable=True)
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)

    items: Mapped[list[SaleItem]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", lazy="selectin"
    )


class SaleItem(Base, LineItemMixin):
    __tablename__ = "sale_items"

    id: Mapped[uuid.UUID] = pk()
    sale_id: Mapped[uuid.UUID] = fk("sales.id")
    #: Null for free-text lines that were never matched to a catalogue product.
    product_id: Mapped[uuid.UUID | None] = fk("products.id", ondelete="SET NULL", nullable=True)

    sale: Mapped[Sale] = relationship(back_populates="items")
