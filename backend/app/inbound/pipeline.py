"""Turning an arriving message into a reviewable draft.

Every channel reduces to the same four facts — who sent it, what it says, a
stable id, and which business it belongs to — and from there the path is shared:

    fetch -> route to a business -> parse with the Smart Input engine
          -> store as `pending` -> a person accepts it on the Inbox page

The parse is the *same* code the internal Smart Input window uses, so a note
mailed in behaves exactly like one typed in, including Hindi and Kannada.

Nothing here writes to the books. Acceptance does, and only a signed-in user
can accept.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Business, ChannelLink, InboundMessage
from ..smart_input import draft_from_text

log = logging.getLogger("smartsme.inbound")

#: Bodies longer than this are almost certainly newsletters or quoted threads;
#: the parser only ever reads the first few lines anyway.
MAX_BODY = 8000

#: Queue states, and how the Inbox page names them.
STATUS_LABELS = {
    "pending": "Needs review",
    "accepted": "Recorded",
    "rejected": "Dismissed",
    "failed": "Could not read",
}


@dataclass(slots=True)
class IncomingMessage:
    """What a channel adapter hands over, before it is routed or parsed."""

    channel: str
    external_id: str
    sender: str
    body: str
    sender_name: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    #: Set when the adapter already knows the business (a linked Telegram chat).
    business_id: uuid.UUID | None = None
    #: Set when routing has to be done by token (an email plus-address).
    token: str | None = None
    #: What a channel link is keyed on, when that differs from `external_id`.
    #: A Telegram chat sends many messages: each needs its own `external_id` to
    #: deduplicate, but they all route by the one chat id.
    route_key: str | None = None


def route(db: Session, message: IncomingMessage) -> uuid.UUID | None:
    """Which business this message belongs to, if any.

    A message that cannot be routed is dropped rather than guessed at — putting
    a stranger's order into somebody's books would be worse than losing it.
    """
    if message.business_id is not None:
        return message.business_id

    if message.token:
        business_id = db.scalar(
            select(Business.id).where(Business.inbox_token == message.token.strip().lower())
        )
        if business_id:
            return business_id

    link = db.scalar(
        select(ChannelLink).where(
            ChannelLink.channel == message.channel,
            ChannelLink.external_id == (message.route_key or message.external_id),
        )
    )
    return link.business_id if link else None


def ingest(db: Session, message: IncomingMessage) -> InboundMessage | None:
    """Store one message as a pending draft. Returns None if it was a duplicate
    or could not be routed."""
    business_id = route(db, message)
    if business_id is None:
        log.info("dropped %s message %s: no business", message.channel, message.external_id)
        return None

    body = (message.body or "").strip()[:MAX_BODY]
    row = InboundMessage(
        business_id=business_id,
        channel=message.channel,
        external_id=message.external_id,
        sender=(message.sender or "")[:320],
        sender_name=message.sender_name,
        subject=(message.subject or None),
        body=body,
        received_at=message.received_at or datetime.now(),
    )

    # The subject often carries the order and the body only a signature, so the
    # parser is given both.
    text = f"{message.subject}. {body}" if message.subject else body
    try:
        row.draft = draft_from_text(db, business_id, text)
        row.status = "pending"
    except ValueError as err:
        # An empty or unreadable message is still worth keeping: someone should
        # see that a customer wrote in, even if nothing could be extracted.
        row.status = "failed"
        row.note = str(err)
    except Exception as err:  # pragma: no cover - defensive
        row.status = "failed"
        row.note = f"Could not parse this message: {err}"
        log.exception("parse failed for %s %s", message.channel, message.external_id)

    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # The unique (business, channel, external_id) constraint caught a
        # re-delivery to this same business.
        db.rollback()
        log.debug("already ingested %s %s", message.channel, message.external_id)
        return None

    db.refresh(row)
    return row


def ingest_many(db: Session, messages: list[IncomingMessage]) -> int:
    return sum(1 for m in messages if ingest(db, m) is not None)
