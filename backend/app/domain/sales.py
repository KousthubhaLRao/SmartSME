"""Sales: creation (outbox pattern), cancellation, and date correction."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.utils import money, round2
from ..events import publish
from ..models import Business, Party, Product, Sale, SaleItem, StockMovement
from ..schemas import SaleInput, SaleTotals
from ..workflow import payment_status_for
from .line_items import assert_party_owned, clean_line_items, load_owned_products

DiscountType = str  # "none" | "amount" | "percentage"


def calculate_sale_totals(
    subtotal: float,
    tax_rate: float,
    discount_type: DiscountType = "none",
    discount_value: float = 0,
) -> SaleTotals:
    """Discount comes off the subtotal *before* tax."""
    safe_subtotal = round2(max(0.0, subtotal))
    if discount_type == "amount":
        discount_amount = round2(max(0.0, discount_value))
    elif discount_type == "percentage":
        discount_amount = round2(safe_subtotal * max(0.0, discount_value) / 100)
    else:
        discount_amount = 0.0
    discounted = round2(max(0.0, safe_subtotal - discount_amount))
    tax = round2(discounted * (tax_rate / 100))
    return SaleTotals(
        subtotal=safe_subtotal,
        discountAmount=discount_amount,
        tax=tax,
        total=round2(discounted + tax),
    )


def create_sale(
    db: Session,
    business_id: uuid.UUID,
    data: SaleInput,
    actor_id: uuid.UUID | None = None,
) -> Sale:
    """Write the sale rows AND the SALE_CREATED event in one transaction.

    The worker then applies inventory and the customer's balance.
    """
    items = clean_line_items(data.items)
    party_id = assert_party_owned(db, business_id, data.partyId)

    # Block overselling up front, so an invoice is never created for stock we do
    # not have. This also rejects productIds belonging to another business.
    products = load_owned_products(db, business_id, items)
    wanted: dict[uuid.UUID, int] = {}
    for it in items:
        if it.productId:
            pid = uuid.UUID(it.productId)
            wanted[pid] = wanted.get(pid, 0) + it.quantity

    shortfalls: list[str] = []
    for pid, need in wanted.items():
        p = products[pid]
        if need > p.stock:
            shortfalls.append(f"{p.name} (in stock: {p.stock} {p.unit}, requested: {need})")
    if shortfalls:
        lead = (
            "Not enough stock to complete this sale:"
            if len(shortfalls) == 1
            else "Not enough stock for these items:"
        )
        raise ValueError(f"{lead} {'; '.join(shortfalls)}. Reduce the quantity or restock first.")

    biz = db.scalar(select(Business).where(Business.id == business_id))
    if biz is None:
        raise ValueError("Business not found.")

    subtotal = round2(sum(i.quantity * i.unitPrice for i in items))
    discount_type = data.discountType or "none"
    discount_value = data.discountValue or 0
    if discount_type != "none" and not discount_value >= 0:
        raise ValueError("Discount can't be negative.")

    totals = calculate_sale_totals(subtotal, biz.tax_rate, discount_type, discount_value)
    # A discount larger than the goods are worth (e.g. 300 off a 200 sale, or a
    # percentage over 100) is rejected rather than silently clamped to zero.
    if discount_type != "none" and totals.discountAmount > round2(subtotal):
        raise ValueError(
            f"Discount ({money(totals.discountAmount, biz.currency)}) is more than the sale value "
            f"({money(subtotal, biz.currency)}). Lower the discount to continue."
        )

    raw_paid = data.amountPaid or 0
    amount_paid = round2(max(0.0, min(raw_paid, totals.total)))
    payment_status = payment_status_for(amount_paid, totals.total)

    count = db.scalar(select(func.count(Sale.id)).where(Sale.business_id == business_id)) or 0
    invoice_number = f"{biz.invoice_prefix}-{count + 1:04d}"

    sale = Sale(
        business_id=business_id,
        party_id=party_id,
        invoice_number=invoice_number,
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
    db.add(sale)
    db.flush()  # assign the sale id

    for i in items:
        db.add(
            SaleItem(
                sale_id=sale.id,
                product_id=uuid.UUID(i.productId) if i.productId else None,
                description=i.description.strip(),
                quantity=i.quantity,
                unit_price=i.unitPrice,
                line_total=round2(i.quantity * i.unitPrice),
            )
        )

    publish(db, business_id, "SALE_CREATED", {"saleId": str(sale.id)}, actor_id)
    db.commit()
    db.refresh(sale)
    return sale


def cancel_sale(db: Session, business_id: uuid.UUID, sale_id: uuid.UUID) -> None:
    """Restore stock, reverse the receivable, and mark the sale cancelled."""
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.business_id == business_id))
    if sale is None or sale.status == "cancelled":
        return

    moves = list(
        db.scalars(
            select(StockMovement).where(
                StockMovement.ref_id == sale_id, StockMovement.reason == "sale"
            )
        )
    )
    for m in moves:
        product = db.scalar(select(Product).where(Product.id == m.product_id))
        if product:
            # m.delta is negative for a sale; subtracting it adds the stock back.
            product.stock = product.stock - m.delta
        db.add(
            StockMovement(
                business_id=business_id,
                product_id=m.product_id,
                delta=-m.delta,
                reason="adjustment",
                ref_type="sale-cancel",
                ref_id=sale_id,
                note=f"Cancelled {sale.invoice_number}",
            )
        )

    due = round2(sale.total - sale.amount_paid)
    if sale.party_id and due != 0:
        party = db.scalar(select(Party).where(Party.id == sale.party_id))
        if party:
            party.balance = round2(party.balance - due)

    sale.status = "cancelled"
    db.commit()


def update_sale_date(
    db: Session, business_id: uuid.UUID, sale_id: uuid.UUID, date: datetime
) -> None:
    """Back-date (or correct) the business date of a sale."""
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.business_id == business_id))
    if sale is None:
        raise ValueError("Sale not found.")
    sale.date = date
    db.commit()
