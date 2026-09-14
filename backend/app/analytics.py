"""Dashboard and report aggregates, ported from `lib/analytics.ts`."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .core.utils import money, round2, start_of_day
from .models import Expense, Party, Product, Purchase, Sale, SaleItem

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _clamp(n: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, round(n)))


def _fmt(n: float) -> str:
    """Compact label for a dashboard breakdown row (no paise)."""
    return money(n, decimals=0)


def calculate_outstanding_total(rows) -> float:
    return round2(sum(max(0.0, r.total - r.amount_paid) for r in rows))


@dataclass(slots=True)
class RevenuePoint:
    label: str
    value: float
    full: str


def get_revenue_series(db: Session, business_id: uuid.UUID, days: int) -> list[RevenuePoint]:
    """Revenue over the last `days`, bucketed to keep the point count readable:
    daily up to ~a month, weekly up to ~3 months, then whole calendar months."""
    now = datetime.now()
    today = start_of_day(now)
    end_exclusive = today + timedelta(days=1)
    buckets: list[tuple[datetime, datetime, str, str]] = []  # start, end, label, full

    if days <= 31:
        for i in range(days - 1, -1, -1):
            start = today - timedelta(days=i)
            buckets.append(
                (
                    start,
                    start + timedelta(days=1),
                    str(start.day),
                    f"{start.day} {MONTHS[start.month - 1]} {start.year}",
                )
            )
    elif days <= 92:
        weeks = -(-days // 7)  # ceil
        for b in range(weeks - 1, -1, -1):
            end = end_exclusive - timedelta(days=b * 7)
            start = end - timedelta(days=7)
            buckets.append(
                (
                    start,
                    end,
                    f"{start.day} {MONTHS[start.month - 1]}",
                    f"Week of {start.day} {MONTHS[start.month - 1]} {start.year}",
                )
            )
    else:
        months = 12 if days >= 330 else max(1, round(days / 30))
        for m in range(months - 1, -1, -1):
            year = now.year
            month = now.month - m
            while month <= 0:
                month += 12
                year -= 1
            start = datetime(year, month, 1)
            end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
            buckets.append((start, end, MONTHS[month - 1], f"{MONTHS[month - 1]} {year}"))

    # Only the window, and only the two columns the buckets need. Loading whole
    # Sale objects for every sale the business had ever made was the single most
    # expensive thing the dashboard did.
    window_start = min(b[0] for b in buckets)
    window_end = max(b[1] for b in buckets)
    rows = db.execute(
        select(Sale.date, Sale.total).where(
            Sale.business_id == business_id,
            Sale.status != "cancelled",
            Sale.date >= window_start,
            Sale.date < window_end,
        )
    ).all()

    values = [0.0] * len(buckets)
    for sale_date, total in rows:
        for idx, (start, end, _, _) in enumerate(buckets):
            if start <= sale_date < end:
                values[idx] = round2(values[idx] + total)
                break

    return [
        RevenuePoint(label=label, value=values[i], full=full)
        for i, (_, _, label, full) in enumerate(buckets)
    ]


def load_overview(db: Session, business_id: uuid.UUID, days: int = 14) -> dict:
    """Everything the dashboard and the report overview show.

    Aggregated in SQL. An earlier version loaded every sale, purchase, expense
    and line item into Python and summed them there: fine for a demo tenant,
    over a second and a half at four thousand sales, and linear from there.
    """
    live_sale = (Sale.business_id == business_id, Sale.status != "cancelled")
    live_purchase = (Purchase.business_id == business_id, Purchase.status != "cancelled")

    sale_totals = db.execute(
        select(
            func.coalesce(func.sum(Sale.total), 0.0),
            func.count(Sale.id),
            # Outstanding never goes negative, the same clamp the Python version used.
            func.coalesce(func.sum(func.greatest(Sale.total - Sale.amount_paid, 0.0)), 0.0),
        ).where(*live_sale)
    ).one()
    total_sales = round2(sale_totals[0])
    sales_count = sale_totals[1]
    receivable_from_sales = round2(sale_totals[2])

    total_purchases = round2(
        db.scalar(select(func.coalesce(func.sum(Purchase.total), 0.0)).where(*live_purchase)) or 0
    )
    total_expenses = round2(
        db.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0.0)).where(
                Expense.business_id == business_id
            )
        )
        or 0
    )

    balances = db.execute(
        select(
            func.coalesce(
                func.sum(Party.balance).filter(Party.type == "customer", Party.balance > 0), 0.0
            ),
            func.coalesce(
                func.sum(Party.balance).filter(Party.type == "supplier", Party.balance > 0), 0.0
            ),
        ).where(Party.business_id == business_id)
    ).one()
    receivable = round2(receivable_from_sales + round2(balances[0]))
    payable = round2(balances[1])

    stock = db.execute(
        select(
            func.coalesce(func.sum(Product.stock * Product.purchase_price), 0.0),
            func.count(Product.id),
            func.count(Product.id).filter(Product.stock > Product.low_stock_threshold),
        ).where(Product.business_id == business_id)
    ).one()
    inventory_value = round2(stock[0])
    product_count = stock[1]
    healthy_stock = stock[2]

    # Cost of goods sold, joined to the product that was sold rather than
    # rebuilt from a dictionary in Python.
    cogs = (
        db.scalar(
            select(func.coalesce(func.sum(SaleItem.quantity * Product.purchase_price), 0.0))
            .select_from(SaleItem)
            .join(Sale, SaleItem.sale_id == Sale.id)
            .join(Product, SaleItem.product_id == Product.id)
            .where(*live_sale)
        )
        or 0
    )
    gross_profit = round2(total_sales - cogs)

    revenue_series = get_revenue_series(db, business_id, days)

    top_products = [
        {"label": label, "value": round2(value), "display": _fmt(value)}
        for label, value in db.execute(
            select(SaleItem.description, func.sum(SaleItem.line_total))
            .select_from(SaleItem)
            .join(Sale, SaleItem.sale_id == Sale.id)
            .where(*live_sale)
            .group_by(SaleItem.description)
            .order_by(func.sum(SaleItem.line_total).desc())
            .limit(5)
        ).all()
    ]

    top_customers = [
        {"label": name, "value": round2(value), "display": _fmt(value)}
        for name, value in db.execute(
            # Grouped by id, not name: two customers can share one, and
            # merging them would overstate whoever they were merged into.
            select(Party.name, func.sum(Sale.total))
            .select_from(Sale)
            .join(Party, Sale.party_id == Party.id)
            .where(*live_sale)
            .group_by(Party.id, Party.name)
            .order_by(func.sum(Sale.total).desc())
            .limit(5)
        ).all()
    ]

    expense_by_category = [
        {"label": category, "value": round2(value), "display": _fmt(value)}
        for category, value in db.execute(
            select(Expense.category, func.sum(Expense.amount))
            .where(Expense.business_id == business_id)
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        ).all()
    ]

    low_stock = list(
        db.scalars(
            select(Product)
            .where(
                Product.business_id == business_id,
                Product.stock <= Product.low_stock_threshold,
            )
            .order_by(Product.stock.asc())
            .limit(20)
        )
    )

    # ---- Business health (heuristic 0-100) ----
    inventory = 100 if not product_count else _clamp(healthy_stock / product_count * 100)

    now = datetime.now()
    cutoff = now - timedelta(days=days)
    prior_cutoff = now - timedelta(days=2 * days)
    windows = db.execute(
        select(
            func.coalesce(func.sum(Sale.total).filter(Sale.date >= cutoff), 0.0),
            func.coalesce(
                func.sum(Sale.total).filter(Sale.date >= prior_cutoff, Sale.date < cutoff), 0.0
            ),
        ).where(*live_sale)
    ).one()
    recent_rev = windows[0]
    prior_rev = windows[1]
    if prior_rev > 0:  # noqa: SIM108 - a nested ternary reads worse here
        growth = (recent_rev - prior_rev) / prior_rev
    else:
        growth = 1 if recent_rev > 0 else 0
    revenue_score = _clamp(60 + growth * 40, 10, 100)

    if total_sales > 0:
        expense_ratio = total_expenses / total_sales
    else:
        expense_ratio = 1 if total_expenses > 0 else 0
    expense_score = _clamp(100 - expense_ratio * 100, 10, 100)

    if payable + receivable == 0:
        cash_flow = 80
    else:
        cash_flow = _clamp(40 + (receivable / (payable + receivable)) * 55, 10, 100)

    overall = _clamp((inventory + revenue_score + expense_score + cash_flow) / 4)

    return {
        "totals": {
            "sales": total_sales,
            "purchases": total_purchases,
            "expenses": total_expenses,
            "receivable": receivable,
            "payable": payable,
            "inventoryValue": inventory_value,
            "grossProfit": gross_profit,
            "salesCount": sales_count,
        },
        "revenueSeries": [
            {"label": r.label, "value": r.value, "full": r.full} for r in revenue_series
        ],
        "topProducts": top_products,
        "topCustomers": top_customers,
        "expenseByCategory": expense_by_category,
        "lowStock": [
            {
                "id": str(p.id),
                "name": p.name,
                "stock": p.stock,
                "unit": p.unit,
                "lowStockThreshold": p.low_stock_threshold,
            }
            for p in low_stock
        ],
        "health": {
            "overall": overall,
            "inventory": inventory,
            "revenue": revenue_score,
            "expense": expense_score,
            "cashFlow": cash_flow,
        },
    }
