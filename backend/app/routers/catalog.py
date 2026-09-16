"""Products, parties and expenses."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from .. import serializers as ser
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..core.utils import round2
from ..domain import catalog
from ..domain.payments import settle_all_outstanding, settle_party
from ..models import Expense, Party, Product, Purchase, Sale, StockMovement
from ..pagination import Paging, page_info, slice_of, total_for
from ..schemas import ExpenseInput, PartyInput, ProductInput, StockAdjustInput
from ..worker import drain_queue

router = APIRouter(prefix="/api", tags=["catalog"])


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
@router.get("/products", dependencies=[Depends(require(P.DATA_READ))])
def list_products(ctx: CurrentUser, db: Db, paging: Paging) -> dict:
    listing = select(Product).where(Product.business_id == ctx.business.id).order_by(Product.name)
    total = total_for(db, listing)
    products = list(db.scalars(slice_of(listing, paging)))

    # Aggregated over the whole catalogue, not just this page.
    stats = db.execute(
        select(
            func.count(Product.id),
            func.coalesce(func.sum(Product.stock * Product.purchase_price), 0.0),
            func.count(Product.id).filter(Product.stock <= Product.low_stock_threshold),
        ).where(Product.business_id == ctx.business.id)
    ).one()

    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.business_id == ctx.business.id)
            .order_by(StockMovement.created_at.desc())
            .limit(40)
        )
    )
    # Movement rows name products that may not be on this page.
    names = dict(
        db.execute(
            select(Product.id, Product.name).where(Product.business_id == ctx.business.id)
        ).all()
    )
    return {
        "rows": [ser.product(p) for p in products],
        "page": page_info(paging, total),
        "movements": [ser.stock_movement(m, names.get(m.product_id)) for m in movements],
        "stats": {
            "count": stats[0],
            "inventoryValue": round2(stats[1]),
            "lowCount": stats[2],
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
        catalog.adjust_stock(db, ctx.business.id, product_id, body.delta, body.note, ctx.user.id)
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
def list_parties(ctx: CurrentUser, db: Db, paging: Paging) -> dict:
    listing = select(Party).where(Party.business_id == ctx.business.id).order_by(Party.name)
    total = total_for(db, listing)
    parties = list(db.scalars(slice_of(listing, paging)))
    page_ids = [p.id for p in parties]

    # Outstanding invoices and bills, so a party row can be expanded to show
    # what makes up its balance. Restricted to the parties actually on this
    # page — this used to read every sale and purchase the business had.
    outstanding: dict[str, list[dict]] = {}

    def collect(rows, ref_attr: str) -> None:
        for row in rows:
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

    if page_ids:
        for model, ref in ((Sale, "invoice_number"), (Purchase, "reference_number")):
            collect(
                db.scalars(
                    select(model)
                    .where(
                        model.business_id == ctx.business.id,
                        model.party_id.in_(page_ids),
                        model.status != "cancelled",
                        model.total > model.amount_paid,
                    )
                    .order_by(model.date.desc())
                ),
                ref,
            )

    # Balances cover every party, not just this page.
    totals = db.execute(
        select(
            func.coalesce(
                func.sum(Party.balance).filter(Party.type == "customer", Party.balance > 0), 0.0
            ),
            func.coalesce(
                func.sum(Party.balance).filter(Party.type == "supplier", Party.balance > 0), 0.0
            ),
        ).where(Party.business_id == ctx.business.id)
    ).one()

    rows = []
    for p in parties:
        item = ser.party(p)
        item["outstanding"] = outstanding.get(str(p.id), [])
        rows.append(item)

    return {
        "rows": rows,
        "page": page_info(paging, total),
        "stats": {"receivable": round2(totals[0]), "payable": round2(totals[1])},
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


@router.post("/parties/{party_id}/settle", dependencies=[Depends(require(P.TXN_WRITE))])
def settle_one(party_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    """Clear one party's outstanding documents in a single step.

    Gated on TXN_WRITE, the same permission as taking a payment against one
    invoice, because that is all this is: the same act, for one party, without
    making the person at the counter click through six bills one at a time.
    Requiring more only meant an employee who could settle a party in six
    clicks could not do it in one, which protected nothing.
    """
    try:
        result = settle_party(db, ctx.business.id, party_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return result.model_dump()


@router.post("/parties/settle-all/{kind}", dependencies=[Depends(require(P.DATA_MANAGE))])
def settle_all(kind: str, ctx: CurrentUser, db: Db) -> dict:
    """Clear every customer, or every supplier, at once.

    This one stays with the owner. It is not bookkeeping for a party someone
    actually dealt with — it writes off balances across the whole business,
    including parties the person clicking has never met, in one irreversible
    step. That is a decision about the books, not a record of a payment.
    """
    if kind not in ("receivable", "payable"):
        raise HTTPException(status_code=400, detail="kind must be receivable or payable.")
    return settle_all_outstanding(db, ctx.business.id, kind).model_dump()


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
@router.get("/expenses", dependencies=[Depends(require(P.DATA_READ))])
def list_expenses(ctx: CurrentUser, db: Db, paging: Paging) -> dict:
    listing = (
        select(Expense).where(Expense.business_id == ctx.business.id).order_by(Expense.date.desc())
    )
    total = total_for(db, listing)
    rows = list(db.scalars(slice_of(listing, paging)))

    stats = db.execute(
        select(
            func.coalesce(func.sum(Expense.amount), 0.0),
            func.count(Expense.id),
            func.count(Expense.id).filter(Expense.flagged.is_not(None)),
        ).where(Expense.business_id == ctx.business.id)
    ).one()

    # The category breakdown is a chart of everything, so it is grouped in SQL.
    by_category = db.execute(
        select(Expense.category, func.coalesce(func.sum(Expense.amount), 0.0))
        .where(Expense.business_id == ctx.business.id)
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    ).all()

    return {
        "rows": [ser.expense(e) for e in rows],
        "page": page_info(paging, total),
        "stats": {"total": round2(stats[0]), "count": stats[1], "flagged": stats[2]},
        "byCategory": [{"label": c, "value": round2(v)} for c, v in by_category],
        "currency": ctx.business.currency,
    }


@router.post("/expenses", status_code=201, dependencies=[Depends(require(P.TXN_WRITE))])
def create_expense(body: ExpenseInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        expense = catalog.create_expense(db, ctx.business.id, body, ctx.user.id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    drain_queue()
    return ser.expense(expense)


@router.delete("/expenses/{expense_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
def delete_expense(expense_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    catalog.delete_expense(db, ctx.business.id, expense_id)
    return {"ok": True}
