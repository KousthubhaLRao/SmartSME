"""Payments: single payments and bulk settlement of receivables/payables."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.utils import round2
from ..models import Party, Purchase, Sale
from ..schemas import SettleResult
from ..workflow import payment_status_for


def record_payment(
    db: Session,
    business_id: uuid.UUID,
    *,
    sale_id: uuid.UUID | None = None,
    purchase_id: uuid.UUID | None = None,
    amount: float,
) -> None:
    """Record money in (sale) or money out (purchase), reducing the party balance."""
    amt = round2(amount)
    if not amt > 0:
        raise ValueError("Amount must be greater than zero.")

    if sale_id is not None:
        # Scoped to the caller's business, so a payment can never be recorded
        # against another tenant's invoice.
        sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.business_id == business_id))
        if sale is None:
            raise ValueError("Sale not found.")
        if sale.status == "cancelled":
            raise ValueError("Cannot record a payment on a cancelled sale.")
        # Snap to the total once the invoice settles, so the party balance never
        # keeps a sub-cent residual that payment_status_for already calls "paid".
        paid = round2(min(sale.amount_paid + amt, sale.total))
        status = payment_status_for(paid, sale.total)
        if status == "paid":
            paid = sale.total
        applied = round2(paid - sale.amount_paid)
        sale.amount_paid = paid
        sale.payment_status = status
        if sale.party_id and applied > 0:
            party = db.scalar(select(Party).where(Party.id == sale.party_id))
            if party:
                party.balance = round2(party.balance - applied)

    elif purchase_id is not None:
        pur = db.scalar(
            select(Purchase).where(Purchase.id == purchase_id, Purchase.business_id == business_id)
        )
        if pur is None:
            raise ValueError("Purchase not found.")
        if pur.status == "cancelled":
            raise ValueError("Cannot record a payment on a cancelled purchase.")
        paid = round2(min(pur.amount_paid + amt, pur.total))
        status = payment_status_for(paid, pur.total)
        if status == "paid":
            paid = pur.total
        applied = round2(paid - pur.amount_paid)
        pur.amount_paid = paid
        pur.payment_status = status
        if pur.party_id and applied > 0:
            party = db.scalar(select(Party).where(Party.id == pur.party_id))
            if party:
                party.balance = round2(party.balance - applied)

    db.commit()


def settle_party(db: Session, business_id: uuid.UUID, party_id: uuid.UUID) -> SettleResult:
    """Settle every outstanding document for one party, then clear its balance.

    The balance is set to zero rather than only reduced by document dues,
    because it may also hold an opening balance with no invoice/bill row.
    """
    party = db.scalar(select(Party).where(Party.id == party_id, Party.business_id == business_id))
    if party is None:
        raise ValueError("Party not found.")

    applied = 0.0
    count = 0

    if party.type == "supplier":
        rows = list(
            db.scalars(
                select(Purchase).where(
                    Purchase.business_id == business_id,
                    Purchase.party_id == party_id,
                    Purchase.status != "cancelled",
                )
            )
        )
    else:
        rows = list(
            db.scalars(
                select(Sale).where(
                    Sale.business_id == business_id,
                    Sale.party_id == party_id,
                    Sale.status != "cancelled",
                )
            )
        )

    for row in rows:
        due = round2(row.total - row.amount_paid)
        if due <= 0:
            continue
        row.amount_paid = row.total
        row.payment_status = "paid"
        applied = round2(applied + due)
        count += 1

    party.balance = 0
    db.commit()
    return SettleResult(count=count, total=applied)


def settle_all_outstanding(db: Session, business_id: uuid.UUID, kind: str) -> SettleResult:
    """Mark every outstanding document of one kind as paid across the business.

    Walk-in documents with no linked party are settled too; the matching
    customer or supplier balances are then cleared, including opening balances.
    """
    applied = 0.0
    count = 0

    if kind == "payable":
        rows = list(
            db.scalars(
                select(Purchase).where(
                    Purchase.business_id == business_id, Purchase.status != "cancelled"
                )
            )
        )
        party_type = "supplier"
    else:
        rows = list(
            db.scalars(
                select(Sale).where(Sale.business_id == business_id, Sale.status != "cancelled")
            )
        )
        party_type = "customer"

    for row in rows:
        due = round2(row.total - row.amount_paid)
        if due <= 0:
            continue
        row.amount_paid = row.total
        row.payment_status = "paid"
        applied = round2(applied + due)
        count += 1

    for party in db.scalars(
        select(Party).where(Party.business_id == business_id, Party.type == party_type)
    ):
        party.balance = 0

    db.commit()
    return SettleResult(count=count, total=applied)
