"""Inventory: products and the append-only stock ledger."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, count, fk, money, pk, timestamp


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sku: Mapped[str | None] = mapped_column(Text)
    hsn: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text, nullable=False, default="pcs", server_default="pcs")
    purchase_price: Mapped[float] = money()
    selling_price: Mapped[float] = money()
    stock: Mapped[int] = count()
    low_stock_threshold: Mapped[int] = count(10)
    created_at: Mapped[datetime] = timestamp()


class StockMovement(Base):
    """Append-only inventory ledger: every change, with its cause."""

    __tablename__ = "stock_movements"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    product_id: Mapped[uuid.UUID] = fk("products.id")
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)  # sale | purchase | adjustment
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp()
