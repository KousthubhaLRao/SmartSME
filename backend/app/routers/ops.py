"""Workflow rules, the event bus monitor, notifications and business settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from .. import serializers as ser
from ..ai.client import ai_status
from ..core.deps import CurrentUser, Db
from ..events import EVENT_LABELS, EVENT_TYPES
from ..models import Event, Notification, WorkflowExecution, WorkflowRule
from ..schemas import RuleInput, SettingsInput
from ..worker import drain_queue

router = APIRouter(prefix="/api", tags=["ops"])


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
@router.get("/workflow")
def get_workflow(ctx: CurrentUser, db: Db) -> dict:
    rules = list(
        db.scalars(
            select(WorkflowRule)
            .where(WorkflowRule.business_id == ctx.business.id)
            # Seeded rules share a created_at, so name breaks the tie and keeps
            # the list order stable between loads.
            .order_by(WorkflowRule.created_at.asc(), WorkflowRule.name.asc())
        )
    )
    executions = list(
        db.scalars(
            select(WorkflowExecution)
            .where(WorkflowExecution.business_id == ctx.business.id)
            .order_by(WorkflowExecution.created_at.desc())
            .limit(30)
        )
    )
    return {
        "rules": [ser.workflow_rule(r) for r in rules],
        "executions": [ser.workflow_execution(x) for x in executions],
        "eventTypes": [{"value": t, "label": EVENT_LABELS[t]} for t in EVENT_TYPES],
    }


@router.post("/workflow/rules", status_code=201)
def create_rule(body: RuleInput, ctx: CurrentUser, db: Db) -> dict:
    if body.eventType not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown event type.")
    rule = WorkflowRule(
        business_id=ctx.business.id,
        name=body.name.strip() or "Untitled rule",
        event_type=body.eventType,
        condition_field=body.conditionField or None,
        condition_op=body.conditionOp or None,
        condition_value=body.conditionValue or None,
        action_type=body.actionType,
        action_config=body.actionConfig or {},
        enabled=body.enabled,
        built_in=False,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return ser.workflow_rule(rule)


@router.put("/workflow/rules/{rule_id}")
def update_rule(rule_id: uuid.UUID, body: RuleInput, ctx: CurrentUser, db: Db) -> dict:
    rule = db.scalar(
        select(WorkflowRule).where(
            WorkflowRule.id == rule_id, WorkflowRule.business_id == ctx.business.id
        )
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    rule.name = body.name.strip() or rule.name
    rule.event_type = body.eventType
    rule.condition_field = body.conditionField or None
    rule.condition_op = body.conditionOp or None
    rule.condition_value = body.conditionValue or None
    rule.action_type = body.actionType
    rule.action_config = body.actionConfig or {}
    rule.enabled = body.enabled
    db.commit()
    return ser.workflow_rule(rule)


@router.post("/workflow/rules/{rule_id}/toggle")
def toggle_rule(rule_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    rule = db.scalar(
        select(WorkflowRule).where(
            WorkflowRule.id == rule_id, WorkflowRule.business_id == ctx.business.id
        )
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    rule.enabled = not rule.enabled
    db.commit()
    return {"id": str(rule.id), "enabled": rule.enabled}


@router.delete("/workflow/rules/{rule_id}")
def delete_rule(rule_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    rule = db.scalar(
        select(WorkflowRule).where(
            WorkflowRule.id == rule_id, WorkflowRule.business_id == ctx.business.id
        )
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    if rule.built_in:
        raise HTTPException(
            status_code=400, detail="Built-in rules can be disabled but not deleted."
        )
    db.delete(rule)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------
@router.get("/events")
def list_events(ctx: CurrentUser, db: Db, status: str | None = Query(None)) -> dict:
    stmt = select(Event).where(Event.business_id == ctx.business.id)
    if status:
        stmt = stmt.where(Event.status == status)
    rows = list(db.scalars(stmt.order_by(Event.created_at.desc()).limit(100)))

    counts = dict(
        db.execute(
            select(Event.status, func.count(Event.id))
            .where(Event.business_id == ctx.business.id)
            .group_by(Event.status)
        ).all()
    )
    return {
        "rows": [ser.event(e) for e in rows],
        "counts": {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "done": counts.get("done", 0),
            "dead": counts.get("dead", 0),
        },
        "eventTypes": [{"value": t, "label": EVENT_LABELS[t]} for t in EVENT_TYPES],
    }


@router.post("/events/{event_id}/replay")
def replay_event(event_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    event = db.scalar(
        select(Event).where(Event.id == event_id, Event.business_id == ctx.business.id)
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    event.status = "pending"
    event.retry_count = 0
    event.error = None
    event.processed_at = None
    db.commit()
    drain_queue()
    return {"ok": True}


@router.post("/events/drain")
def drain(ctx: CurrentUser) -> dict:
    """Process anything still pending (also useful as a cron target)."""
    return {"processed": drain_queue()}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@router.get("/notifications")
def list_notifications(ctx: CurrentUser, db: Db) -> dict:
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.business_id == ctx.business.id)
            .order_by(Notification.created_at.desc())
            .limit(100)
        )
    )
    unread = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.business_id == ctx.business.id, Notification.read.is_(False)
        )
    )
    return {"rows": [ser.notification(n) for n in rows], "unread": unread or 0}


@router.get("/notifications/unread-count")
def unread_count(ctx: CurrentUser, db: Db) -> dict:
    n = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.business_id == ctx.business.id, Notification.read.is_(False)
        )
    )
    return {"unread": n or 0}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    n = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.business_id == ctx.business.id
        )
    )
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    n.read = True
    db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read(ctx: CurrentUser, db: Db) -> dict:
    for n in db.scalars(
        select(Notification).where(
            Notification.business_id == ctx.business.id, Notification.read.is_(False)
        )
    ):
        n.read = True
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@router.get("/settings")
def get_settings(ctx: CurrentUser) -> dict:
    b = ctx.business
    return {
        "business": {
            "name": b.name,
            "gstNumber": b.gst_number,
            "panNumber": b.pan_number,
            "address": b.address,
            "phone": b.phone,
            "email": b.email,
            "currency": b.currency,
            "taxRate": b.tax_rate,
            "invoicePrefix": b.invoice_prefix,
        },
        "ai": ai_status(),
    }


@router.put("/settings")
def update_settings(body: SettingsInput, ctx: CurrentUser, db: Db) -> dict:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Business name is required.")
    if not 0 <= body.taxRate <= 100:
        raise HTTPException(status_code=400, detail="Tax rate must be between 0 and 100.")
    b = db.merge(ctx.business)
    b.name = body.name.strip()
    b.gst_number = body.gstNumber or None
    b.pan_number = body.panNumber or None
    b.address = body.address or None
    b.phone = body.phone or None
    b.email = body.email or None
    b.currency = body.currency or "INR"
    b.tax_rate = body.taxRate
    b.invoice_prefix = (body.invoicePrefix or "INV").strip()
    db.commit()
    return {"ok": True}
