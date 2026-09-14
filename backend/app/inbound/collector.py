"""The sweep that collects from every configured channel.

Called on a schedule (Celery beat in celery mode, the worker thread otherwise)
and from `POST /api/inbox/collect` so it can be triggered by hand.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import Business, ChannelLink
from . import email as email_channel
from . import telegram as telegram_channel
from .pipeline import IncomingMessage, ingest

log = logging.getLogger("smartsme.inbound")

#: Telegram acknowledges by offset. Keeping it in memory is enough: the unique
#: (business, channel, external_id) constraint makes a re-read after a restart
#: harmless.
_telegram_offset: int | None = None

LINK_HELP = (
    "This chat is not linked to a business yet.\n\n"
    "Open SmartSME, go to Settings, copy your inbox token, and send:\n"
    "/link <your-token>"
)


def collect(db: Session) -> dict[str, int]:
    """Collect from every enabled channel. Returns a per-channel count of what
    was newly queued."""
    return {
        "email": _collect_email(db),
        "telegram": _collect_telegram(db),
    }


def _collect_email(db: Session) -> int:
    if not settings.email_ingest_enabled:
        return 0
    return sum(1 for message in email_channel.fetch() if ingest(db, message) is not None)


def _collect_telegram(db: Session) -> int:
    global _telegram_offset
    if not telegram_channel.enabled():
        return 0

    queued = 0
    for update in telegram_channel.get_updates(offset=_telegram_offset):
        queued += _handle_update(db, update)

        # Acknowledged once the update has been dealt with - whatever "dealt
        # with" turned out to mean. There is exactly one place this advances,
        # and getting it wrong goes badly in both directions:
        #
        #   advance too early  a failed insert loses the order for good, since
        #                      Telegram never re-sends an acknowledged update;
        #   advance too late   an update nothing can ever read - a photo, a
        #                      sticker, someone joining the chat - pins the
        #                      offset, and the bot re-reads it and everything
        #                      after it every thirty seconds for a day.
        #
        # After the work and before the next update is the only spot that is
        # right for both: an exception leaves the offset where it was, and an
        # update that simply had nothing in it still moves on.
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            _telegram_offset = update_id + 1

    return queued


def _handle_update(db: Session, update: dict) -> int:
    """Deal with one update; returns 1 if it was queued for review."""
    parsed = telegram_channel.to_incoming(update)
    if parsed is None:
        return 0

    chat_id = parsed.external_id
    message_id = (update.get("message") or {}).get("message_id")
    # Dedup on the message, route on the chat.
    parsed.route_key = chat_id
    parsed.external_id = f"{chat_id}:{message_id or update.get('update_id')}"

    token = telegram_channel.link_token_in(parsed.body)
    if token:
        _link_chat(db, chat_id, token, parsed.sender_name)
        return 0

    if ingest(db, parsed) is not None:
        return 1
    if _unlinked(db, chat_id):
        telegram_channel.send_message(chat_id, LINK_HELP)
    return 0


def _unlinked(db: Session, chat_id: str) -> bool:
    return (
        db.scalar(
            select(ChannelLink.id).where(
                ChannelLink.channel == "telegram", ChannelLink.external_id == chat_id
            )
        )
        is None
    )


def _link_chat(db: Session, chat_id: str, token: str, label: str | None) -> None:
    """Bind a chat to the business whose inbox token was sent."""
    business = db.scalar(select(Business).where(Business.inbox_token == token))
    if business is None:
        telegram_channel.send_message(chat_id, "That token does not match any business.")
        return

    existing = db.scalar(
        select(ChannelLink).where(
            ChannelLink.channel == "telegram", ChannelLink.external_id == chat_id
        )
    )
    if existing is None:
        db.add(
            ChannelLink(
                business_id=business.id,
                channel="telegram",
                external_id=chat_id,
                label=label,
            )
        )
    else:
        existing.business_id = business.id
        existing.label = label or existing.label
    db.commit()
    telegram_channel.send_message(
        chat_id,
        f"Linked to {business.name}. Send an order as a normal message and it will "
        f"appear in the SmartSME inbox for review.",
    )


__all__ = ["IncomingMessage", "collect"]
