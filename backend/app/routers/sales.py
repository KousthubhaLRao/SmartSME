"""Sales: list, create, detail, payment, cancel, date correction."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from .. import serializers as ser
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..core.utils import parse_date_input, round2
from ..domain import sales as sales_domain
from ..domain.payments import record_payment
from ..models import Party, Product, Sale, SaleItem
from ..pagination import Paging, page_info, slice_of, total_for
from ..schemas import DateInput, PaymentInput, SaleInput
from ..worker import drain_queue

router = APIRouter(prefix="/api/sales", tags=["sales"])


@router.get("", dependencies=[Depends(require(P.DATA_READ))])
def list_sales(ctx: CurrentUser, db: Db, paging: Paging) -> dict:
    listing = (
        select(Sale, Party.name)
        .join(Party, Sale.party_id == Party.id, isouter=True)
        .where(Sale.business_id == ctx.business.id)
        .order_by(Sale.date.desc())
    )
    total = total_for(db, listing)
    rows = list(db.execute(slice_of(listing, paging)).all())

    # Aggregated over every sale, not just this page.
    stats = db.execute(
        select(
            func.coalesce(func.sum(Sale.total), 0.0),
            func.coalesce(func.sum(Sale.total - Sale.amount_paid), 0.0),
            func.count(Sale.id),
        ).where(Sale.business_id == ctx.business.id, Sale.status != "cancelled")
    ).one()

    products = list(
        db.scalars(
            select(Product).where(Product.business_id == ctx.business.id).order_by(Product.name)
        )
    )
    customers = list(
        db.scalars(
            select(Party)
            .where(Party.business_id == ctx.business.id, Party.type == "customer")
            .order_by(Party.name)
        )
    )
    return {
        "rows": [ser.sale_row(s, name) for s, name in rows],
        "page": page_info(paging, total),
        "stats": {
            "totalSales": round2(stats[0]),
            "receivable": round2(stats[1]),
            "count": stats[2],
        },
        "products": [ser.product(p) for p in products],
        "customers": [{"id": str(c.id), "name": c.name} for c in customers],
        "taxRate": ctx.business.tax_rate,
        "currency": ctx.business.currency,
    }


@router.post("", status_code=201, dependencies=[Depends(require(P.TXN_WRITE))])
def create_sale(body: SaleInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        sale = sales_domain.create_sale(db, ctx.business.id, body, ctx.user.id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    # Apply the event chain now, so the client sees updated stock/balances.
    drain_queue()
    return {"id": str(sale.id), "invoiceNumber": sale.invoice_number}


@router.get("/{sale_id}", dependencies=[Depends(require(P.DATA_READ))])
def get_sale(sale_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.business_id == ctx.business.id))
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found.")
    party = db.scalar(select(Party).where(Party.id == sale.party_id)) if sale.party_id else None
    items = list(db.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)))
    detail = ser.sale_detail(sale, party, items)
    detail["business"] = {
        "name": ctx.business.name,
        "address": ctx.business.address,
        "gstNumber": ctx.business.gst_number,
        "currency": ctx.business.currency,
    }
    return detail


@router.post("/{sale_id}/payment", dependencies=[Depends(require(P.TXN_WRITE))])
def pay_sale(sale_id: uuid.UUID, body: PaymentInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        record_payment(db, ctx.business.id, sale_id=sale_id, amount=body.amount)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"ok": True}


@router.post("/{sale_id}/cancel", dependencies=[Depends(require(P.DATA_MANAGE))])
def cancel_sale(sale_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    sales_domain.cancel_sale(db, ctx.business.id, sale_id)
    return {"ok": True}


@router.patch("/{sale_id}/date", dependencies=[Depends(require(P.DATA_MANAGE))])
def set_sale_date(sale_id: uuid.UUID, body: DateInput, ctx: CurrentUser, db: Db) -> dict:
    date = parse_date_input(body.date)
    if date is None:
        raise HTTPException(status_code=400, detail="Pick a valid date.")
    try:
        sales_domain.update_sale_date(db, ctx.business.id, sale_id, date)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"ok": True}
