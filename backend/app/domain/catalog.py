"""Products, parties and expenses: validation plus their side effects."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.utils import round2
from ..events import publish
from ..models import Expense, Party, Product, PurchaseItem, SaleItem, StockMovement
from ..schemas import ExpenseInput, PartyInput, ProductInput

# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


def _non_negative_money(v: float | None, label: str) -> float:
    n = float(v or 0)
    if n != n or n < 0:  # NaN or negative
        raise ValueError(f"{label} must be a number of zero or more.")
    return n


def _non_negative_int(v: int | None, fallback: int, label: str) -> int:
    n = int(v if v is not None else fallback)
    if n < 0:
        raise ValueError(f"{label} must be a whole number of zero or more.")
    return n


def create_product(db: Session, business_id: uuid.UUID, data: ProductInput) -> Product:
    if not data.name.strip():
        raise ValueError("Product name is required.")
    product = Product(
        business_id=business_id,
        name=data.name.strip(),
        sku=data.sku or None,
        hsn=data.hsn or None,
        unit=data.unit or "pcs",
        purchase_price=_non_negative_money(data.purchasePrice, "Purchase price"),
        selling_price=_non_negative_money(data.sellingPrice, "Selling price"),
        stock=_non_negative_int(data.stock, 0, "Opening stock"),
        low_stock_threshold=_non_negative_int(data.lowStockThreshold, 10, "Low-stock threshold"),
    )
    db.add(product)
    db.flush()
    if product.stock > 0:
        db.add(
            StockMovement(
                business_id=business_id,
                product_id=product.id,
                delta=product.stock,
                reason="adjustment",
                note="Opening stock",
            )
        )
    db.commit()
    db.refresh(product)
    return product


def update_product(
    db: Session, business_id: uuid.UUID, product_id: uuid.UUID, data: ProductInput
) -> None:
    if not data.name.strip():
        raise ValueError("Product name is required.")
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.business_id == business_id)
    )
    if product is None:
        raise ValueError("Product not found.")
    product.name = data.name.strip()
    product.sku = data.sku or None
    product.hsn = data.hsn or None
    product.unit = data.unit or "pcs"
    product.purchase_price = _non_negative_money(data.purchasePrice, "Purchase price")
    product.selling_price = _non_negative_money(data.sellingPrice, "Selling price")
    product.low_stock_threshold = _non_negative_int(
        data.lowStockThreshold, 10, "Low-stock threshold"
    )
    db.commit()


def adjust_stock(
    db: Session,
    business_id: uuid.UUID,
    product_id: uuid.UUID,
    delta: int,
    note: str,
    actor_id: uuid.UUID | None = None,
) -> None:
    """A manual stock correction. Emits STOCK_UPDATED so low-stock re-evaluates."""
    if delta == 0:
        raise ValueError("Enter a non-zero quantity.")
    d = int(delta)
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.business_id == business_id)
    )
    if product is None:
        raise ValueError("Product not found.")
    # Never let a manual adjustment drive stock below zero.
    if product.stock + d < 0:
        raise ValueError(
            f"That adjustment would take {product.name} to {product.stock + d} {product.unit}. "
            f"Only {product.stock} {product.unit} in stock."
        )
    product.stock = product.stock + d
    db.add(
        StockMovement(
            business_id=business_id,
            product_id=product_id,
            delta=d,
            reason="adjustment",
            note=note or "Manual adjustment",
        )
    )
    publish(
        db,
        business_id,
        "STOCK_UPDATED",
        {"productId": str(product_id), "cause": "adjustment"},
        actor_id,
    )
    db.commit()


def delete_product(db: Session, business_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """Refuse to delete a product that appears on past invoices.

    Cascading the delete would strip it from those lines and erase its stock
    history. Products that were only ever stocked can go.
    """
    on_sale = db.scalar(select(SaleItem.id).where(SaleItem.product_id == product_id).limit(1))
    on_purchase = db.scalar(
        select(PurchaseItem.id).where(PurchaseItem.product_id == product_id).limit(1)
    )
    if on_sale or on_purchase:
        raise ValueError(
            "This product appears on past invoices and can't be deleted. "
            "Set its stock to zero to retire it instead."
        )
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.business_id == business_id)
    )
    if product:
        db.delete(product)
        db.commit()


# ---------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------


_PHONE_RE = re.compile(r"^\+?[0-9]+$")


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    cleaned = re.sub(r"[\s-]", "", phone.strip())
    if not cleaned:
        return None
    if not _PHONE_RE.match(cleaned):
        raise ValueError("Phone number can only contain digits and an optional leading +")
    return cleaned


def create_party(db: Session, business_id: uuid.UUID, data: PartyInput) -> Party:
    if not data.name.strip():
        raise ValueError("Name is required.")
    party = Party(
        business_id=business_id,
        type="supplier" if data.type == "supplier" else "customer",
        name=data.name.strip(),
        phone=_normalize_phone(data.phone),
        email=data.email or None,
        gst_number=data.gstNumber or None,
        address=data.address or None,
        balance=float(data.openingBalance or 0),
    )
    db.add(party)
    db.commit()
    db.refresh(party)
    return party


def update_party(
    db: Session, business_id: uuid.UUID, party_id: uuid.UUID, data: PartyInput
) -> None:
    if not data.name.strip():
        raise ValueError("Name is required.")
    party = db.scalar(select(Party).where(Party.id == party_id, Party.business_id == business_id))
    if party is None:
        raise ValueError("Party not found.")
    party.type = "supplier" if data.type == "supplier" else "customer"
    party.name = data.name.strip()
    party.phone = _normalize_phone(data.phone)
    party.email = data.email or None
    party.gst_number = data.gstNumber or None
    party.address = data.address or None
    db.commit()


def delete_party(db: Session, business_id: uuid.UUID, party_id: uuid.UUID) -> None:
    party = db.scalar(select(Party).where(Party.id == party_id, Party.business_id == business_id))
    if party:
        db.delete(party)
        db.commit()


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


def create_expense(
    db: Session,
    business_id: uuid.UUID,
    data: ExpenseInput,
    actor_id: uuid.UUID | None = None,
) -> Expense:
    if not data.description.strip():
        raise ValueError("Description is required.")
    if not data.amount > 0:
        raise ValueError("Amount must be greater than zero.")

    expense = Expense(
        business_id=business_id,
        category=data.category.strip() or "General",
        description=data.description.strip(),
        amount=round2(data.amount),
        date=data.date or datetime.now(),
    )
    db.add(expense)
    db.flush()
    publish(db, business_id, "EXPENSE_ADDED", {"expenseId": str(expense.id)}, actor_id)
    db.commit()
    db.refresh(expense)
    return expense


def delete_expense(db: Session, business_id: uuid.UUID, expense_id: uuid.UUID) -> None:
    expense = db.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.business_id == business_id)
    )
    if expense:
        db.delete(expense)
        db.commit()
