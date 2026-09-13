"""Products, parties and expenses."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .. import serializers as ser
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..core.utils import round2
from ..domain import catalog
from ..domain.payments import settle_all_outstanding, settle_party
from ..models import Expense, Party, Product, Purchase, Sale, StockMovement
from ..schemas import ExpenseInput, PartyInput, ProductInput, StockAdjustInput
from ..worker import drain_queue

router = APIRouter(prefix="/api", tags=["catalog"])


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
@router.get("/products", dependencies=[Depends(require(P.DATA_READ))])
def list_products(ctx: CurrentUser, db: Db) -> dict:
    products = list(
        db.scalars(
            select(Product).where(Product.business_id == ctx.business.id).order_by(Product.name)
        )
    )
    names = {p.id: p.name for p in products}
    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.business_id == ctx.business.id)
            .order_by(StockMovement.created_at.desc())
            .limit(40)
        )
    )
    return {
        "rows": [ser.product(p) for p in products],
        "movements": [ser.stock_movement(m, names.get(m.product_id)) for m in movements],
        "stats": {
            "count": len(products),
            "inventoryValue": round2(sum(p.stock * p.purchase_price for p in products)),
            "lowCount": sum(1 for p in products if p.stock <= p.low_stock_threshold),
        },
        "currency": ctx.business.currency,
    }


@router.post("/products", status_code=201, dependencies=[Depends(require(P.CATALOG_WRITE))])
def create_product(body: ProductInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        product = catalog.create_product(db, ctx.business.id, body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return ser.product(product)


@router.put("/products/{product_id}", dependencies=[Depends(require(P.CATALOG_WRITE))])
def update_product(product_id: uuid.UUID, body: ProductInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        catalog.update_product(db, ctx.business.id, product_id, body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"ok": True}


@router.post("/products/{product_id}/adjust", dependencies=[Depends(require(P.TXN_WRITE))])
def adjust_stock(product_id: uuid.UUID, body: StockAdjustInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        catalog.adjust_stock(db, ctx.business.id, product_id, body.delta, body.note)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    drain_queue()
    return {"ok": True}


@router.delete("/products/{product_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
def delete_product(product_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    try:
        catalog.delete_product(db, ctx.business.id, product_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"ok": True}


# ---------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------
@router.get("/parties", dependencies=[Depends(require(P.DATA_READ))])
def list_parties(ctx: CurrentUser, db: Db) -> dict:
    parties = list(
        db.scalars(select(Party).where(Party.business_id == ctx.business.id).order_by(Party.name))
    )

    # Outstanding invoices/bills, so each party row can be expanded to show what
    # makes up its balance and settled in bulk.
    outstanding: dict[str, list[dict]] = {}

    def collect(rows, ref_attr: str) -> None:
        for row in rows:
            if not row.party_id:
                continue
            due = round2(row.total - row.amount_paid)
            if due <= 0.001:
                continue
            outstanding.setdefault(str(row.party_id), []).append(
                {
                    "id": str(row.id),
                    "ref": getattr(row, ref_attr),
                    "date": row.date.isoformat(),
                    "total": row.total,
                    "due": due,
                }
            )

    collect(
        db.scalars(
            select(Sale)
            .where(Sale.business_id == ctx.business.id, Sale.status != "cancelled")
            .order_by(Sale.date.desc())
        ),
        "invoice_number",
    )
    collect(
        db.scalars(
            select(Purchase)
            .where(Purchase.business_id == ctx.business.id, Purchase.status != "cancelled")
            .order_by(Purchase.date.desc())
        ),
        "reference_number",
    )

    rows = []
    for p in parties:
        item = ser.party(p)
        item["outstanding"] = outstanding.get(str(p.id), [])
        rows.append(item)

    return {
        "rows": rows,
        "stats": {
            "receivable": round2(
                sum(p.balance for p in parties if p.type == "customer" and p.balance > 0)
            ),
            "payable": round2(
                sum(p.balance for p in parties if p.type == "supplier" and p.balance > 0)
            ),
        },
        "currency": ctx.business.currency,
    }


@router.post("/parties", status_code=201, dependencies=[Depends(require(P.CATALOG_WRITE))])
def create_party(body: PartyInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        party = catalog.create_party(db, ctx.business.id, body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return ser.party(party)


@router.put("/parties/{party_id}", dependencies=[Depends(require(P.CATALOG_WRITE))])
def update_party(party_id: uuid.UUID, body: PartyInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        catalog.update_party(db, ctx.business.id, party_id, body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"ok": True}


@router.delete("/parties/{party_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
def delete_party(party_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    catalog.delete_party(db, ctx.business.id, party_id)
    return {"ok": True}


@router.post("/parties/{party_id}/settle", dependencies=[Depends(require(P.DATA_MANAGE))])
def settle_one(party_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    try:
        result = settle_party(db, ctx.business.id, party_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return result.model_dump()


@router.post("/parties/settle-all/{kind}", dependencies=[Depends(require(P.DATA_MANAGE))])
def settle_all(kind: str, ctx: CurrentUser, db: Db) -> dict:
    if kind not in ("receivable", "payable"):
        raise HTTPException(status_code=400, detail="kind must be receivable or payable.")
    return settle_all_outstanding(db, ctx.business.id, kind).model_dump()


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
@router.get("/expenses", dependencies=[Depends(require(P.DATA_READ))])
def list_expenses(ctx: CurrentUser, db: Db) -> dict:
    rows = list(
        db.scalars(
            select(Expense)
            .where(Expense.business_id == ctx.business.id)
            .order_by(Expense.date.desc())
        )
    )
    by_category: dict[str, float] = {}
    for e in rows:
        by_category[e.category] = round2(by_category.get(e.category, 0) + e.amount)
    return {
        "rows": [ser.expense(e) for e in rows],
        "stats": {
            "total": round2(sum(e.amount for e in rows)),
            "count": len(rows),
            "flagged": sum(1 for e in rows if e.flagged),
        },
        "byCategory": [
            {"label": k, "value": v} for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])
        ],
        "currency": ctx.business.currency,
    }


@router.post("/expenses", status_code=201, dependencies=[Depends(require(P.TXN_WRITE))])
def create_expense(body: ExpenseInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        expense = catalog.create_expense(db, ctx.business.id, body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    drain_queue()
    return ser.expense(expense)


@router.delete("/expenses/{expense_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
def delete_expense(expense_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    catalog.delete_expense(db, ctx.business.id, expense_id)
    return {"ok": True}
