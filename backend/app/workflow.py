"""Workflow engine: always-on core effects plus configurable WHEN/THEN rules.

Ported from `lib/workflow/engine.ts`. Every event is handled inside ONE
transaction, so its effects (inventory, balances, chained events, alerts) either
all commit or all roll back. That makes automatic retries safe: a failed attempt
leaves nothing half-applied.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.utils import money, round2
from .events import publish
from .models import (
    Event,
    Expense,
    Notification,
    Party,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    StockMovement,
    WorkflowExecution,
    WorkflowRule,
)


def payment_status_for(paid: float, total: float) -> str:
    if paid <= 0:
        return "unpaid"
    if paid >= total - 0.01:
        return "paid"
    return "partial"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _notify(
    db: Session,
    business_id: uuid.UUID,
    *,
    type_: str,
    title: str,
    message: str,
    severity: str = "info",
    dedupe: bool = False,
) -> None:
    if dedupe:
        existing = db.scalar(
            select(Notification.id)
            .where(
                Notification.business_id == business_id,
                Notification.title == title,
                Notification.read.is_(False),
            )
            .limit(1)
        )
        if existing:
            return
    db.add(
        Notification(
            business_id=business_id,
            type=type_,
            severity=severity,
            title=title,
            message=message,
        )
    )


def _record_execution(
    db: Session,
    business_id: uuid.UUID,
    rule: WorkflowRule,
    event: Event,
    status: str,
    detail: str,
) -> None:
    db.add(
        WorkflowExecution(
            business_id=business_id,
            rule_id=rule.id,
            rule_name=rule.name,
            event_id=event.id,
            event_type=event.type,
            status=status,
            detail=detail,
        )
    )


def _condition_met(rule: WorkflowRule, ctx: dict[str, Any]) -> bool:
    if not rule.condition_field or not rule.condition_op or rule.condition_value is None:
        return True
    # Fail closed when the field is absent, so a "not equal" rule cannot match
    # on a field the event simply does not carry.
    if rule.condition_field not in ctx or ctx[rule.condition_field] is None:
        return False
    raw = ctx[rule.condition_field]
    target = rule.condition_value
    try:
        a, b = float(raw), float(target)
        numeric = True
    except (TypeError, ValueError):
        a = b = 0.0
        numeric = False

    op = rule.condition_op
    if op == "gt":
        return numeric and a > b
    if op == "gte":
        return numeric and a >= b
    if op == "lt":
        return numeric and a < b
    if op == "lte":
        return numeric and a <= b
    if op == "eq":
        return str(raw) == str(target)
    if op == "neq":
        return str(raw) != str(target)
    return True


# ---------------------------------------------------------------------------
# Core, always-on effects (inventory + balances), not rule-gated
# ---------------------------------------------------------------------------
def _apply_sale(db: Session, event: Event) -> int:
    sale_id = uuid.UUID(str(event.payload["saleId"]))
    sale = db.scalar(select(Sale).where(Sale.id == sale_id))
    if not sale:
        raise RuntimeError(f"Sale not found: {sale_id}")
    # A sale cancelled before its create event was applied must not move stock
    # or balances (cancel_sale already reverses anything applied).
    if sale.status == "cancelled":
        return 0

    items = list(db.scalars(select(SaleItem).where(SaleItem.sale_id == sale_id)))

    # Replay guard: if stock movements already exist for this sale, an earlier
    # run applied it. Skip so a manual replay cannot double-apply.
    prior = db.scalar(select(StockMovement.id).where(StockMovement.ref_id == sale.id).limit(1))
    if prior and any(i.product_id for i in items):
        return len(items)

    affected: set[uuid.UUID] = set()
    for it in items:
        if not it.product_id:
            continue
        product = db.scalar(select(Product).where(Product.id == it.product_id))
        if not product:
            continue
        product.stock = product.stock - it.quantity
        db.add(
            StockMovement(
                business_id=event.business_id,
                product_id=it.product_id,
                delta=-it.quantity,
                reason="sale",
                ref_type="sale",
                ref_id=sale.id,
                note=sale.invoice_number,
            )
        )
        affected.add(it.product_id)

    due = round2(sale.total - sale.amount_paid)
    if sale.party_id and due != 0:
        party = db.scalar(select(Party).where(Party.id == sale.party_id))
        if party:
            party.balance = round2(party.balance + due)

    # Chained events, written in the same transaction so they are never lost.
    for product_id in affected:
        publish(
            db,
            event.business_id,
            "STOCK_UPDATED",
            {"productId": str(product_id), "cause": "sale", "refId": str(sale.id)},
            event.user_id,
        )
    return len(items)


def _apply_purchase(db: Session, event: Event) -> int:
    purchase_id = uuid.UUID(str(event.payload["purchaseId"]))
    pur = db.scalar(select(Purchase).where(Purchase.id == purchase_id))
    if not pur:
        raise RuntimeError(f"Purchase not found: {purchase_id}")
    if pur.status == "cancelled":
        return 0

    items = list(db.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)))

    prior = db.scalar(select(StockMovement.id).where(StockMovement.ref_id == pur.id).limit(1))
    if prior and any(i.product_id for i in items):
        return len(items)

    affected: set[uuid.UUID] = set()
    for it in items:
        if not it.product_id:
            continue
        product = db.scalar(select(Product).where(Product.id == it.product_id))
        if not product:
            continue
        product.stock = product.stock + it.quantity
        db.add(
            StockMovement(
                business_id=event.business_id,
                product_id=it.product_id,
                delta=it.quantity,
                reason="purchase",
                ref_type="purchase",
                ref_id=pur.id,
                note=pur.reference_number,
            )
        )
        affected.add(it.product_id)

    due = round2(pur.total - pur.amount_paid)
    if pur.party_id and due != 0:
        party = db.scalar(select(Party).where(Party.id == pur.party_id))
        if party:
            party.balance = round2(party.balance + due)

    for product_id in affected:
        publish(
            db,
            event.business_id,
            "STOCK_UPDATED",
            {"productId": str(product_id), "cause": "purchase", "refId": str(pur.id)},
            event.user_id,
        )
    return len(items)


def _apply_core_effects(db: Session, event: Event) -> int:
    if event.type in ("SALE_CREATED", "ORDER_CREATED"):
        return _apply_sale(db, event)
    if event.type == "PURCHASE_CREATED":
        return _apply_purchase(db, event)
    return 0


# ---------------------------------------------------------------------------
# Rule context
# ---------------------------------------------------------------------------
def _build_context(db: Session, event: Event) -> dict[str, Any]:
    out: dict[str, Any] = {"ctx": {}, "product": None, "expense_id": None, "summary": event.type}

    if event.type in ("SALE_CREATED", "ORDER_CREATED"):
        sale = db.scalar(select(Sale).where(Sale.id == uuid.UUID(str(event.payload["saleId"]))))
        if not sale:
            return {**out, "summary": "sale"}
        party = db.scalar(select(Party).where(Party.id == sale.party_id)) if sale.party_id else None
        out["ctx"] = {
            "amount": sale.total,
            "total": sale.total,
            "subtotal": sale.subtotal,
            "paymentStatus": sale.payment_status,
            "source": sale.source,
        }
        out["summary"] = (
            f"{sale.invoice_number} · {party.name if party else 'walk-in'} · {money(sale.total)}"
        )
        return out

    if event.type == "PURCHASE_CREATED":
        pur = db.scalar(
            select(Purchase).where(Purchase.id == uuid.UUID(str(event.payload["purchaseId"])))
        )
        if not pur:
            return {**out, "summary": "purchase"}
        out["ctx"] = {
            "amount": pur.total,
            "total": pur.total,
            "paymentStatus": pur.payment_status,
            "source": pur.source,
        }
        out["summary"] = f"{pur.reference_number} · {money(pur.total)}"
        return out

    if event.type == "STOCK_UPDATED":
        product = db.scalar(
            select(Product).where(Product.id == uuid.UUID(str(event.payload["productId"])))
        )
        if not product:
            return {**out, "summary": "stock update"}
        out["ctx"] = {"stock": product.stock, "threshold": product.low_stock_threshold}
        out["product"] = product
        out["summary"] = f"{product.name} · {product.stock} {product.unit}"
        return out

    if event.type == "EXPENSE_ADDED":
        expense = db.scalar(
            select(Expense).where(Expense.id == uuid.UUID(str(event.payload["expenseId"])))
        )
        if not expense:
            return {**out, "summary": "expense"}
        out["ctx"] = {
            "amount": expense.amount,
            "category": expense.category,
            "description": expense.description,
        }
        out["expense_id"] = expense.id
        out["summary"] = f"{expense.category} · {expense.description} · {money(expense.amount)}"
        return out

    out["ctx"] = dict(event.payload or {})
    return out


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def _execute_action(db: Session, rule: WorkflowRule, event: Event, extras: dict[str, Any]) -> None:
    cfg = rule.action_config or {}
    bid = event.business_id

    if rule.action_type == "update_inventory":
        _record_execution(
            db,
            bid,
            rule,
            event,
            "matched",
            f"Inventory updated for {extras['affected_count']} item(s)",
        )
        return

    if rule.action_type == "restock_alert":
        product: Product | None = extras.get("product")
        if not product:
            _record_execution(db, bid, rule, event, "skipped", "No product in context")
            return
        if product.stock <= 0:
            _notify(
                db,
                bid,
                type_="low_stock",
                severity="error",
                title=f"Out of stock: {product.name}",
                message=f"{product.name} has run out. Restock to keep selling.",
                dedupe=True,
            )
            _record_execution(db, bid, rule, event, "matched", f"Out of stock: {product.name}")
        elif product.stock <= product.low_stock_threshold:
            _notify(
                db,
                bid,
                type_="low_stock",
                severity="warning",
                title=f"Low stock: {product.name}",
                message=(
                    f"Only {product.stock} {product.unit} left "
                    f"(threshold {product.low_stock_threshold}). Consider restocking."
                ),
                dedupe=True,
            )
            _record_execution(
                db, bid, rule, event, "matched", f"Low stock: {product.name} ({product.stock})"
            )
        else:
            _record_execution(
                db, bid, rule, event, "skipped", f"Stock healthy: {product.name} ({product.stock})"
            )
        return

    if rule.action_type == "flag_expense":
        expense_id = extras.get("expense_id")
        if not expense_id:
            _record_execution(db, bid, rule, event, "skipped", "No expense in context")
            return
        label = cfg.get("label") or "Flagged by workflow"
        expense = db.scalar(select(Expense).where(Expense.id == expense_id))
        if expense:
            expense.flagged = label
        _notify(
            db,
            bid,
            type_="workflow",
            severity="warning",
            title=cfg.get("title") or rule.name,
            message=extras["summary"],
            dedupe=True,
        )
        _record_execution(db, bid, rule, event, "matched", label)
        return

    # "notify" and anything unrecognised
    _notify(
        db,
        bid,
        type_="workflow",
        severity=cfg.get("severity") or "info",
        title=cfg.get("title") or rule.name,
        message=extras["summary"],
        dedupe=True,
    )
    _record_execution(db, bid, rule, event, "matched", "Notification created")


# ---------------------------------------------------------------------------
# Entry point, called by the worker for each claimed event
# ---------------------------------------------------------------------------
def run_workflow_rules(db: Session, event: Event) -> None:
    affected_count = _apply_core_effects(db, event)
    built = _build_context(db, event)

    rules = list(
        db.scalars(
            select(WorkflowRule).where(
                WorkflowRule.business_id == event.business_id,
                WorkflowRule.event_type == event.type,
                WorkflowRule.enabled.is_(True),
            )
        )
    )

    for rule in rules:
        if not _condition_met(rule, built["ctx"]):
            _record_execution(db, event.business_id, rule, event, "skipped", "Condition not met")
            continue
        _execute_action(
            db,
            rule,
            event,
            {
                "product": built["product"],
                "expense_id": built["expense_id"],
                "affected_count": affected_count,
                "summary": built["summary"],
            },
        )


def default_rules(business_id: uuid.UUID) -> list[WorkflowRule]:
    """The rule set every new business starts with."""
    return [
        WorkflowRule(
            business_id=business_id,
            name="Update inventory on sale",
            event_type="SALE_CREATED",
            action_type="update_inventory",
            built_in=True,
            action_config={},
        ),
        WorkflowRule(
            business_id=business_id,
            name="Low-stock restock alert",
            event_type="STOCK_UPDATED",
            action_type="restock_alert",
            built_in=True,
            action_config={},
        ),
        WorkflowRule(
            business_id=business_id,
            name="Flag high-value expense",
            event_type="EXPENSE_ADDED",
            condition_field="amount",
            condition_op="gt",
            condition_value="10000",
            action_type="flag_expense",
            action_config={"label": "High-value expense, needs review"},
        ),
        WorkflowRule(
            business_id=business_id,
            name="Unpaid sale reminder",
            event_type="SALE_CREATED",
            condition_field="paymentStatus",
            condition_op="eq",
            condition_value="unpaid",
            action_type="notify",
            action_config={"title": "Payment pending", "severity": "warning"},
        ),
    ]
