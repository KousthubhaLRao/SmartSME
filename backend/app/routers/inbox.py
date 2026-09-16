"""The review queue for orders that arrived from outside.

Reading the queue needs `data:read`. Everything that decides the fate of a
message - accepting it, dismissing it, or fetching more - needs `txn:write`, the
same permission as recording a sale by hand, because that is what those are.
Deleting from the queue needs `data:manage`, like any other destruction.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select

from ..core.config import settings
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..inbound import telegram as telegram_channel
from ..inbound.collector import collect
from ..inbound.pipeline import STATUS_LABELS
from ..models import ChannelLink, InboundMessage
from ..pagination import Paging, page_info, slice_of, total_for
from ..smart_input import publish_draft
from ..worker import drain_queue

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


def _channel_status() -> dict:
    """What is switched on, for the page to say plainly."""
    return {
        "email": settings.email_ingest_enabled,
        "telegram": telegram_channel.enabled(),
    }


def _row(message: InboundMessage) -> dict:
    return {
        "id": str(message.id),
        "channel": message.channel,
        "sender": message.sender,
        "senderName": message.sender_name,
        "subject": message.subject,
        "body": message.body,
        "status": message.status,
        "statusLabel": STATUS_LABELS.get(message.status, message.status),
        "draft": message.draft,
        "note": message.note,
        "receivedAt": message.received_at.isoformat(),
        "handledAt": message.handled_at.isoformat() if message.handled_at else None,
    }


@router.get("", dependencies=[Depends(require(P.DATA_READ))])
def list_inbox(
    ctx: CurrentUser,
    db: Db,
    paging: Paging,
    status: str | None = Query(None),
) -> dict:
    listing = select(InboundMessage).where(InboundMessage.business_id == ctx.business.id)
    if status:
        if status not in STATUS_LABELS:
            raise HTTPException(status_code=400, detail="Unknown status.")
        listing = listing.where(InboundMessage.status == status)
    listing = listing.order_by(InboundMessage.received_at.desc())

    total = total_for(db, listing)
    rows = list(db.scalars(slice_of(listing, paging)))

    counts = dict(
        db.execute(
            select(InboundMessage.status, func.count(InboundMessage.id))
            .where(InboundMessage.business_id == ctx.business.id)
            .group_by(InboundMessage.status)
        ).all()
    )
    links = list(db.scalars(select(ChannelLink).where(ChannelLink.business_id == ctx.business.id)))
    return {
        "rows": [_row(m) for m in rows],
        "page": page_info(paging, total),
        "counts": {s: counts.get(s, 0) for s in STATUS_LABELS},
        "pending": counts.get("pending", 0),
        "inboxToken": ctx.business.inbox_token,
        "inboxAddress": f"orders+{ctx.business.inbox_token}@{settings.inbox_domain}",
        # Which channels are actually switched on. Without this the page cannot
        # tell "no new mail" from "nobody is collecting mail", and those look
        # identical from the outside - which is exactly how an afternoon gets
        # spent wondering why a message sitting in Mailpit never arrives.
        "channels": _channel_status(),
        "links": [
            {
                "id": str(link.id),
                "channel": link.channel,
                "label": link.label,
                "externalId": link.external_id,
            }
            for link in links
        ],
    }


@router.get("/pending-count", dependencies=[Depends(require(P.DATA_READ))])
def pending_count(ctx: CurrentUser, db: Db) -> dict:
    """How many messages are waiting for a decision. One COUNT, nothing else.

    This is what the sidebar badge polls from every page, so it is kept to a
    single indexed count rather than reusing the list route: nobody should pay
    for drafts, channel links and a page of rows to learn that the number is
    still zero.
    """
    n = db.scalar(
        select(func.count(InboundMessage.id)).where(
            InboundMessage.business_id == ctx.business.id,
            InboundMessage.status == "pending",
        )
    )
    return {"pending": n or 0}


@router.post("/collect", dependencies=[Depends(require(P.TXN_WRITE))])
def collect_now(ctx: CurrentUser, db: Db) -> dict:
    """Sweep every configured channel immediately, rather than waiting for the
    scheduled poll. Useful on the Inbox page and in tests.

    `txn:write`, not `data:read`: this creates rows. It is also the permission
    an admin does not hold, and an admin has no business filling a tenant's
    queue.

    The sweep itself is necessarily global - one mailbox serves every business,
    and a message is routed by the token it was addressed to - but the counts
    that come back are this business's own. Returning the global tally told
    whoever pressed the button how much traffic other tenants were getting.
    """
    mine = select(func.count(InboundMessage.id)).where(
        InboundMessage.business_id == ctx.business.id
    )
    before = db.scalar(mine) or 0
    collect(db)
    after = db.scalar(mine) or 0
    return {
        "checked": True,
        "queued": after - before,
        "pending": db.scalar(mine.where(InboundMessage.status == "pending")) or 0,
        "channels": _channel_status(),
    }


@router.post("/{message_id}/accept", dependencies=[Depends(require(P.TXN_WRITE))])
def accept(message_id: uuid.UUID, payload: dict[str, Any], ctx: CurrentUser, db: Db) -> dict:
    """Record the message as a real document.

    The body is the (possibly corrected) draft from the review screen — the
    person accepting can fix anything the parser got wrong first, which is the
    whole point of the queue.
    """
    message = _pending_or_404(db, ctx, message_id)

    draft = payload or message.draft
    if not draft:
        raise HTTPException(status_code=400, detail="Nothing to record from this message.")

    # How the order reached the shop is the channel it actually arrived on, not
    # whatever the review screen echoed back. Without this every inbound order
    # is stored as if somebody had typed it into Smart Input, and the ledger
    # cannot tell an emailed order from a Telegram one from a typed one.
    draft = {**draft, "source": message.channel}

    try:
        result = publish_draft(db, ctx.business.id, draft, ctx.user.id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    message.status = "accepted"
    message.handled_by = ctx.user.id
    message.handled_at = datetime.now()
    message.draft = draft
    db.commit()
    drain_queue()
    return {"ok": True, **result}


@router.post("/{message_id}/reject", dependencies=[Depends(require(P.TXN_WRITE))])
def reject(message_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    """Dismiss it. The row stays, so the Inbox remains a record of what arrived.

    Gated the same as accepting. Dismissing an order is a decision about a
    business's data - the customer wrote in and nothing came of it - so it needs
    the permission that lets someone record one, not merely read the queue.
    """
    message = _pending_or_404(db, ctx, message_id)
    message.status = "rejected"
    message.handled_by = ctx.user.id
    message.handled_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.delete("/{message_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
def remove(message_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    message = db.scalar(
        select(InboundMessage).where(
            InboundMessage.id == message_id,
            InboundMessage.business_id == ctx.business.id,
        )
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    db.delete(message)
    db.commit()
    return {"ok": True}


@router.post("/clear-handled", dependencies=[Depends(require(P.DATA_MANAGE))])
def clear_handled(ctx: CurrentUser, db: Db) -> dict:
    removed = db.execute(
        delete(InboundMessage).where(
            InboundMessage.business_id == ctx.business.id,
            InboundMessage.status.in_(("accepted", "rejected")),
        )
    ).rowcount
    db.commit()
    return {"removed": removed or 0}


@router.delete("/links/{link_id}", dependencies=[Depends(require(P.CONFIG_WRITE))])
def unlink(link_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    link = db.scalar(
        select(ChannelLink).where(
            ChannelLink.id == link_id, ChannelLink.business_id == ctx.business.id
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found.")
    db.delete(link)
    db.commit()
    return {"ok": True}


def _pending_or_404(db: Db, ctx: CurrentUser, message_id: uuid.UUID) -> InboundMessage:
    """The message, locked, if it is still waiting for a decision.

    The row is locked because an owner and an employee both have the Inbox open
    on the same order, and both see the same Accept button. Without the lock
    they can each read `pending`, each publish, and the shop ends up with the
    order recorded twice. With it, the second one waits, re-reads `accepted`
    and is told the message has already been dealt with.
    """
    message = db.scalar(
        select(InboundMessage)
        .where(
            InboundMessage.id == message_id,
            InboundMessage.business_id == ctx.business.id,
        )
        .with_for_update()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found.")
    if message.status in ("accepted", "rejected"):
        raise HTTPException(status_code=409, detail="This message has already been dealt with.")
    return message
