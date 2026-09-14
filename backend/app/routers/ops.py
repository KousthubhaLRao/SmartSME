"""Workflow rules, the event bus monitor, notifications and business settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select

from .. import serializers as ser
from ..ai.client import ai_status
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..events import EVENT_LABELS, EVENT_TYPES
from ..models import Event, Notification, User, WorkflowExecution, WorkflowRule
from ..pagination import Paging, page_info, slice_of, total_for
from ..schemas import RuleInput, SettingsInput
from ..worker import drain_queue

router = APIRouter(prefix="/api", tags=["ops"])


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
@router.get("/workflow", dependencies=[Depends(require(P.DATA_READ))])
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


@router.post("/workflow/rules", status_code=201, dependencies=[Depends(require(P.CONFIG_WRITE))])
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


@router.put("/workflow/rules/{rule_id}", dependencies=[Depends(require(P.CONFIG_WRITE))])
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


@router.post("/workflow/rules/{rule_id}/toggle", dependencies=[Depends(require(P.CONFIG_WRITE))])
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


@router.delete("/workflow/rules/{rule_id}", dependencies=[Depends(require(P.CONFIG_WRITE))])
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
@router.get("/events", dependencies=[Depends(require(P.DATA_READ))])
def list_events(ctx: CurrentUser, db: Db, paging: Paging, status: str | None = Query(None)) -> dict:
    stmt = select(Event).where(Event.business_id == ctx.business.id)
    if status:
        stmt = stmt.where(Event.status == status)
    stmt = stmt.order_by(Event.created_at.desc())
    total = total_for(db, stmt)
    rows = list(db.scalars(slice_of(stmt, paging)))

    # One lookup for the whole page, rather than one per row.
    actor_ids = {e.user_id for e in rows if e.user_id}
    actors = (
        dict(db.execute(select(User.id, User.name).where(User.id.in_(actor_ids))).all())
        if actor_ids
        else {}
    )

    counts = dict(
        db.execute(
            select(Event.status, func.count(Event.id))
            .where(Event.business_id == ctx.business.id)
            .group_by(Event.status)
        ).all()
    )
    return {
        "rows": [ser.event(e, actors.get(e.user_id)) for e in rows],
        "page": page_info(paging, total),
        "counts": {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "done": counts.get("done", 0),
            "dead": counts.get("dead", 0),
        },
        "eventTypes": [{"value": t, "label": EVENT_LABELS[t]} for t in EVENT_TYPES],
    }


@router.post("/events/{event_id}/replay", dependencies=[Depends(require(P.EVENTS_OPERATE))])
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


@router.post("/events/drain", dependencies=[Depends(require(P.EVENTS_OPERATE))])
def drain(ctx: CurrentUser) -> dict:
    """Process anything still pending (also useful as a cron target)."""
    return {"processed": drain_queue()}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
SEVERITIES = ("info", "warning", "error")


@router.get("/notifications", dependencies=[Depends(require(P.DATA_READ))])
def list_notifications(
    ctx: CurrentUser,
    db: Db,
    paging: Paging,
    severity: str | None = Query(None),
    unread: bool = Query(False),
) -> dict:
    """The alert log. Filterable, because a shop with a noisy rule needs to be
    able to find the one alert that matters."""
    if severity and severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail="Unknown severity.")

    listing = select(Notification).where(Notification.business_id == ctx.business.id)
    if severity:
        listing = listing.where(Notification.severity == severity)
    if unread:
        listing = listing.where(Notification.read.is_(False))
    listing = listing.order_by(Notification.created_at.desc())

    total = total_for(db, listing)
    rows = list(db.scalars(slice_of(listing, paging)))

    # Resolve every alert's origin in one pass: which rule fired, on which
    # event, and — through the event — who caused it.
    rule_ids = {n.rule_id for n in rows if n.rule_id}
    event_ids = {n.event_id for n in rows if n.event_id}
    rules = (
        dict(
            db.execute(
                select(WorkflowRule.id, WorkflowRule.name).where(WorkflowRule.id.in_(rule_ids))
            ).all()
        )
        if rule_ids
        else {}
    )
    events = (
        {e.id: e for e in db.scalars(select(Event).where(Event.id.in_(event_ids)))}
        if event_ids
        else {}
    )
    actor_ids = {e.user_id for e in events.values() if e.user_id}
    actors = (
        dict(db.execute(select(User.id, User.name).where(User.id.in_(actor_ids))).all())
        if actor_ids
        else {}
    )

    def source_of(n: Notification) -> dict | None:
        e = events.get(n.event_id) if n.event_id else None
        rule_name = rules.get(n.rule_id) if n.rule_id else None
        if e is None and rule_name is None:
            return None
        return {
            "rule": rule_name,
            "eventType": e.type if e else None,
            "actor": actors.get(e.user_id) if e and e.user_id else None,
        }

    counts = dict(
        db.execute(
            select(Notification.severity, func.count(Notification.id))
            .where(Notification.business_id == ctx.business.id)
            .group_by(Notification.severity)
        ).all()
    )
    unread_total = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.business_id == ctx.business.id, Notification.read.is_(False)
        )
    )
    return {
        "rows": [ser.notification(n, source_of(n)) for n in rows],
        "page": page_info(paging, total),
        "unread": unread_total or 0,
        "severities": [{"value": s, "count": counts.get(s, 0)} for s in SEVERITIES],
    }


@router.get("/notifications/unread-count", dependencies=[Depends(require(P.DATA_READ))])
def unread_count(ctx: CurrentUser, db: Db) -> dict:
    n = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.business_id == ctx.business.id, Notification.read.is_(False)
        )
    )
    return {"unread": n or 0}


@router.post("/notifications/{notification_id}/read", dependencies=[Depends(require(P.DATA_READ))])
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


@router.post(
    "/notifications/{notification_id}/unread", dependencies=[Depends(require(P.DATA_READ))]
)
def mark_unread(notification_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    """Put an alert back, for when it was cleared before it was dealt with."""
    n = _notification_or_404(db, ctx, notification_id)
    n.read = False
    db.commit()
    return {"ok": True}


@router.delete("/notifications/{notification_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
def dismiss(notification_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    db.delete(_notification_or_404(db, ctx, notification_id))
    db.commit()
    return {"ok": True}


@router.post("/notifications/clear-read", dependencies=[Depends(require(P.DATA_MANAGE))])
def clear_read(ctx: CurrentUser, db: Db) -> dict:
    """Drop everything already dealt with, leaving the outstanding alerts."""
    removed = db.execute(
        delete(Notification).where(
            Notification.business_id == ctx.business.id, Notification.read.is_(True)
        )
    ).rowcount
    db.commit()
    return {"removed": removed or 0}


@router.post("/notifications/read-all", dependencies=[Depends(require(P.DATA_READ))])
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
def _notification_or_404(db: Db, ctx: CurrentUser, notification_id: uuid.UUID) -> Notification:
    n = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.business_id == ctx.business.id
        )
    )
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return n


@router.get("/settings", dependencies=[Depends(require(P.DATA_READ))])
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


@router.put("/settings", dependencies=[Depends(require(P.CONFIG_WRITE))])
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
