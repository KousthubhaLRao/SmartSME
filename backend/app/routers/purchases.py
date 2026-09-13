"""Purchases: list, create, detail, payment, cancel, date correction."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .. import serializers as ser
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..core.utils import parse_date_input, round2
from ..domain import purchases as purchases_domain
from ..domain.payments import record_payment
from ..models import Party, Product, Purchase, PurchaseItem
from ..schemas import DateInput, PaymentInput, PurchaseInput
from ..worker import drain_queue

router = APIRouter(prefix="/api/purchases", tags=["purchases"])


@router.get("", dependencies=[Depends(require(P.DATA_READ))])
def list_purchases(ctx: CurrentUser, db: Db) -> dict:
    rows = list(
        db.execute(
            select(Purchase, Party.name)
            .join(Party, Purchase.party_id == Party.id, isouter=True)
            .where(Purchase.business_id == ctx.business.id)
            .order_by(Purchase.date.desc())
        ).all()
    )
    active = [p for p, _ in rows if p.status != "cancelled"]
    products = list(
        db.scalars(
            select(Product).where(Product.business_id == ctx.business.id).order_by(Product.name)
        )
    )
    suppliers = list(
        db.scalars(
            select(Party)
            .where(Party.business_id == ctx.business.id, Party.type == "supplier")
            .order_by(Party.name)
        )
    )
    return {
        "rows": [ser.purchase_row(p, name) for p, name in rows],
        "stats": {
            "totalPurchases": round2(sum(p.total for p in active)),
            "payable": round2(sum(p.total - p.amount_paid for p in active)),
            "count": len(active),
        },
        "products": [ser.product(p) for p in products],
        "suppliers": [{"id": str(s.id), "name": s.name} for s in suppliers],
        "taxRate": ctx.business.tax_rate,
        "currency": ctx.business.currency,
    }


@router.post("", status_code=201, dependencies=[Depends(require(P.TXN_WRITE))])
def create_purchase(body: PurchaseInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        purchase = purchases_domain.create_purchase(db, ctx.business.id, body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    drain_queue()
    return {"id": str(purchase.id), "referenceNumber": purchase.reference_number}


@router.get("/{purchase_id}", dependencies=[Depends(require(P.DATA_READ))])
def get_purchase(purchase_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    pur = db.scalar(
        select(Purchase).where(Purchase.id == purchase_id, Purchase.business_id == ctx.business.id)
    )
    if pur is None:
        raise HTTPException(status_code=404, detail="Purchase not found.")
    party = db.scalar(select(Party).where(Party.id == pur.party_id)) if pur.party_id else None
    items = list(db.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id == pur.id)))
    return ser.purchase_detail(pur, party, items)


@router.post("/{purchase_id}/payment", dependencies=[Depends(require(P.TXN_WRITE))])
def pay_purchase(purchase_id: uuid.UUID, body: PaymentInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        record_payment(db, ctx.business.id, purchase_id=purchase_id, amount=body.amount)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"ok": True}


@router.post("/{purchase_id}/cancel", dependencies=[Depends(require(P.DATA_MANAGE))])
def cancel_purchase(purchase_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    purchases_domain.cancel_purchase(db, ctx.business.id, purchase_id)
    return {"ok": True}


@router.patch("/{purchase_id}/date", dependencies=[Depends(require(P.DATA_MANAGE))])
def set_purchase_date(purchase_id: uuid.UUID, body: DateInput, ctx: CurrentUser, db: Db) -> dict:
    date = parse_date_input(body.date)
    if date is None:
        raise HTTPException(status_code=400, detail="Pick a valid date.")
    try:
        purchases_domain.update_purchase_date(db, ctx.business.id, purchase_id, date)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"ok": True}
