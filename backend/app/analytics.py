"""Dashboard and report aggregates, ported from `lib/analytics.ts`."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
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
    sales = list(
        db.scalars(select(Sale).where(Sale.business_id == business_id, Sale.status != "cancelled"))
    )

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

    values = [0.0] * len(buckets)
    for sale in sales:
        for idx, (start, end, _, _) in enumerate(buckets):
            if start <= sale.date < end:
                values[idx] = round2(values[idx] + sale.total)
                break

    return [
        RevenuePoint(label=label, value=values[i], full=full)
        for i, (_, _, label, full) in enumerate(buckets)
    ]


def load_overview(db: Session, business_id: uuid.UUID, days: int = 14) -> dict:
    sales = list(
        db.scalars(select(Sale).where(Sale.business_id == business_id, Sale.status != "cancelled"))
    )
    purchases = list(
        db.scalars(
            select(Purchase).where(
                Purchase.business_id == business_id, Purchase.status != "cancelled"
            )
        )
    )
    expenses = list(db.scalars(select(Expense).where(Expense.business_id == business_id)))
    products = list(db.scalars(select(Product).where(Product.business_id == business_id)))
    parties = list(db.scalars(select(Party).where(Party.business_id == business_id)))

    sale_items = list(
        db.execute(
            select(SaleItem, Sale.party_id)
            .join(Sale, SaleItem.sale_id == Sale.id)
            .where(Sale.business_id == business_id, Sale.status != "cancelled")
        ).all()
    )

    total_sales = round2(sum(s.total for s in sales))
    total_purchases = round2(sum(p.total for p in purchases))
    total_expenses = round2(sum(e.amount for e in expenses))

    receivable_from_sales = calculate_outstanding_total(sales)
    receivable_from_parties = round2(
        sum(p.balance for p in parties if p.type == "customer" and p.balance > 0)
    )
    receivable = round2(receivable_from_sales + receivable_from_parties)
    payable = round2(sum(p.balance for p in parties if p.type == "supplier" and p.balance > 0))
    inventory_value = round2(sum(p.stock * p.purchase_price for p in products))

    # Gross profit estimate = sold-quantity revenue minus its cost of goods.
    product_by_id = {p.id: p for p in products}
    cogs = 0.0
    for item, _party_id in sale_items:
        p = product_by_id.get(item.product_id) if item.product_id else None
        cogs += (p.purchase_price if p else 0) * item.quantity
    gross_profit = round2(total_sales - cogs)

    revenue_series = get_revenue_series(db, business_id, days)

    # Top products by revenue
    prod_agg: dict[str, float] = {}
    for item, _ in sale_items:
        prod_agg[item.description] = prod_agg.get(item.description, 0) + item.line_total
    top_products = [
        {"label": k, "value": round2(v), "display": _fmt(v)}
        for k, v in sorted(prod_agg.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    # Top customers by sales total
    cust_agg: dict[uuid.UUID, float] = {}
    for s in sales:
        if s.party_id:
            cust_agg[s.party_id] = cust_agg.get(s.party_id, 0) + s.total
    name_by_id = {p.id: p.name for p in parties}
    top_customers = [
        {"label": name_by_id.get(k, "Unknown"), "value": round2(v), "display": _fmt(v)}
        for k, v in sorted(cust_agg.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    # Expenses by category
    cat_agg: dict[str, float] = {}
    for e in expenses:
        cat_agg[e.category] = cat_agg.get(e.category, 0) + e.amount
    expense_by_category = [
        {"label": k, "value": round2(v), "display": _fmt(v)}
        for k, v in sorted(cat_agg.items(), key=lambda kv: kv[1], reverse=True)
    ]

    low_stock = sorted(
        (p for p in products if p.stock <= p.low_stock_threshold), key=lambda p: p.stock
    )

    # ---- Business health (heuristic 0-100) ----
    healthy_stock = sum(1 for p in products if p.stock > p.low_stock_threshold)
    inventory = 100 if not products else _clamp(healthy_stock / len(products) * 100)

    now = datetime.now()
    cutoff = now - timedelta(days=days)
    prior_cutoff = now - timedelta(days=2 * days)
    recent_rev = sum(s.total for s in sales if s.date >= cutoff)
    prior_rev = sum(s.total for s in sales if prior_cutoff <= s.date < cutoff)
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
            "salesCount": len(sales),
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
