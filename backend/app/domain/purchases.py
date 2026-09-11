"""Purchases: creation (outbox pattern), cancellation, and date correction."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.utils import money, round2
from ..events import publish
from ..models import Business, Party, Product, Purchase, PurchaseItem, StockMovement
from ..schemas import PurchaseInput, PurchaseTotals
from ..workflow import payment_status_for
from .line_items import assert_party_owned, clean_line_items, load_owned_products


def calculate_purchase_totals(
    subtotal: float,
    tax_rate: float,
    discount_type: str = "none",
    discount_value: float = 0,
) -> PurchaseTotals:
    safe_subtotal = round2(max(0.0, subtotal))
    if discount_type == "amount":
        discount_amount = round2(max(0.0, discount_value))
    elif discount_type == "percentage":
        discount_amount = round2(safe_subtotal * max(0.0, discount_value) / 100)
    else:
        discount_amount = 0.0
    discounted = round2(max(0.0, safe_subtotal - discount_amount))
    tax = round2(discounted * (tax_rate / 100))
    return PurchaseTotals(
        subtotal=safe_subtotal,
        discountAmount=discount_amount,
        tax=tax,
        total=round2(discounted + tax),
    )


def create_purchase(db: Session, business_id: uuid.UUID, data: PurchaseInput) -> Purchase:
    items = clean_line_items(data.items)
    party_id = assert_party_owned(db, business_id, data.partyId)
    # Rejects any productId that does not belong to the business before it can
    # add stock to another tenant's inventory.
    load_owned_products(db, business_id, items)

    biz = db.scalar(select(Business).where(Business.id == business_id))
    if biz is None:
        raise ValueError("Business not found.")

    subtotal = round2(sum(i.quantity * i.unitPrice for i in items))
    discount_type = data.discountType or "none"
    discount_value = data.discountValue or 0
    if discount_type != "none" and not discount_value >= 0:
        raise ValueError("Discount must be a valid positive number.")

    totals = calculate_purchase_totals(subtotal, biz.tax_rate, discount_type, discount_value)
    if discount_type != "none" and totals.discountAmount > round2(subtotal):
        raise ValueError(
            f"Discount ({money(totals.discountAmount, biz.currency)}) is more than the "
            f"purchase value ({money(subtotal, biz.currency)}). Lower the discount to continue."
        )

    amount_paid = round2(max(0.0, min(data.amountPaid or 0, totals.total)))
    payment_status = payment_status_for(amount_paid, totals.total)

    count = (
        db.scalar(select(func.count(Purchase.id)).where(Purchase.business_id == business_id)) or 0
    )
    reference_number = f"PO-{count + 1:04d}"

    purchase = Purchase(
        business_id=business_id,
        party_id=party_id,
        reference_number=reference_number,
        subtotal=totals.subtotal,
        discount_type=discount_type,
        discount_value=discount_value,
        discount_amount=totals.discountAmount,
        tax=totals.tax,
        total=totals.total,
        amount_paid=amount_paid,
        payment_status=payment_status,
        source=data.source or "form",
        notes=data.notes or None,
        date=data.date or datetime.now(),
    )
    db.add(purchase)
    db.flush()

    for i in items:
        db.add(
            PurchaseItem(
                purchase_id=purchase.id,
                product_id=uuid.UUID(i.productId) if i.productId else None,
                description=i.description.strip(),
                quantity=i.quantity,
                unit_price=i.unitPrice,
                line_total=round2(i.quantity * i.unitPrice),
            )
        )

    publish(db, business_id, "PURCHASE_CREATED", {"purchaseId": str(purchase.id)})
    db.commit()
    db.refresh(purchase)
    return purchase


def cancel_purchase(db: Session, business_id: uuid.UUID, purchase_id: uuid.UUID) -> None:
    """Remove the received stock and reverse the payable."""
    pur = db.scalar(
        select(Purchase).where(Purchase.id == purchase_id, Purchase.business_id == business_id)
    )
    if pur is None or pur.status == "cancelled":
        return

    moves = list(
        db.scalars(
            select(StockMovement).where(
                StockMovement.ref_id == purchase_id, StockMovement.reason == "purchase"
            )
        )
    )
    for m in moves:
        product = db.scalar(select(Product).where(Product.id == m.product_id))
        if product:
            product.stock = product.stock - m.delta
        db.add(
            StockMovement(
                business_id=business_id,
                product_id=m.product_id,
                delta=-m.delta,
                reason="adjustment",
                ref_type="purchase-cancel",
                ref_id=purchase_id,
                note=f"Cancelled {pur.reference_number}",
            )
        )

    due = round2(pur.total - pur.amount_paid)
    if pur.party_id and due != 0:
        party = db.scalar(select(Party).where(Party.id == pur.party_id))
        if party:
            party.balance = round2(party.balance - due)

    pur.status = "cancelled"
    db.commit()


def update_purchase_date(
    db: Session, business_id: uuid.UUID, purchase_id: uuid.UUID, date: datetime
) -> None:
    pur = db.scalar(
        select(Purchase).where(Purchase.id == purchase_id, Purchase.business_id == business_id)
    )
    if pur is None:
        raise ValueError("Purchase not found.")
    pur.date = date
    db.commit()
