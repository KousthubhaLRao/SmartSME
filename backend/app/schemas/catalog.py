"""Products, parties, expenses and stock adjustments."""

from __future__ import annotations

from pydantic import BaseModel

from .common import BusinessDate


class ProductInput(BaseModel):
    """Used for both create and update; every field is replaced on update."""

    name: str
    sku: str | None = None
    hsn: str | None = None
    unit: str = "pcs"
    purchasePrice: float = 0
    sellingPrice: float = 0
    stock: int = 0
    lowStockThreshold: int = 10


class PartyInput(BaseModel):
    """A customer or supplier. `openingBalance` seeds what they already owe."""

    type: str = "customer"  # customer | supplier
    name: str
    phone: str | None = None
    email: str | None = None
    gstNumber: str | None = None
    address: str | None = None
    openingBalance: float = 0


class ExpenseInput(BaseModel):
    category: str = "General"
    description: str
    amount: float
    date: BusinessDate = None
    source: str = "form"


class StockAdjustInput(BaseModel):
    """A manual stock correction; `delta` may be negative."""

    delta: int
    note: str = ""
