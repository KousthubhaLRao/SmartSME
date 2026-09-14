"""Orders arriving from outside: email and messaging channels.

Every inbound message lands here first and stays here until a person accepts
it. Nothing external can write to a business's books unattended — the parsed
draft is a *suggestion* on the Inbox page, exactly like the one Smart Input
shows before you confirm it.

The row is kept after acceptance rather than deleted, so the Inbox doubles as a
record of what arrived, what it was read as, and what came of it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, fk, pk, timestamp

#: Where a message came from.
CHANNELS = ("email", "telegram")

#: pending  — parsed, waiting for someone to look at it
#: accepted — turned into a sale/purchase/expense
#: rejected — dismissed as spam or noise
#: failed   — could not be parsed at all
STATUSES = ("pending", "accepted", "rejected", "failed")


class InboundMessage(Base):
    __tablename__ = "inbound_messages"
    __table_args__ = (
        # The same email or Telegram update must never be ingested twice, however
        # often the poller runs or restarts mid-batch.
        #
        # Scoped to the business, because the id belongs to the channel and not
        # to us: one supplier mailing the same order to two shops sends one
        # Message-ID, and a global constraint let the first shop to be polled
        # swallow it while the second never saw the order at all.
        UniqueConstraint(
            "business_id",
            "channel",
            "external_id",
            name="uq_inbound_business_channel_external",
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()

    #: email | telegram
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    #: The channel's own id for this message — a Message-ID header, or a
    #: Telegram update id. The deduplication key.
    external_id: Mapped[str] = mapped_column(Text, nullable=False)

    #: Who sent it, as the channel reports them: an email address, or a Telegram
    #: @handle. Matched against the party list when the draft is built.
    sender: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sender_name: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    #: The draft `smart_input` produced, ready for the confirm screen. Null when
    #: parsing failed.
    draft: Mapped[dict | None] = mapped_column(JSONB)
    #: Why parsing failed, or why it was rejected.
    note: Mapped[str | None] = mapped_column(Text)

    #: Who dealt with it, and when.
    handled_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime)

    received_at: Mapped[datetime] = timestamp()
    created_at: Mapped[datetime] = timestamp()


class ChannelLink(Base):
    """A messaging account bound to a business.

    Telegram has no way of knowing which shop a chat belongs to, so the owner
    sends the bot `/link <token>` once and the chat is bound from then on.
    """

    __tablename__ = "channel_links"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_channel_link_external"),)

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    #: The chat id, for replying and for matching later messages.
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    linked_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    created_at: Mapped[datetime] = timestamp()
