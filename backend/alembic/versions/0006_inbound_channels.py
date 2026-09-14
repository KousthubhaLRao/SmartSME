"""Inbound orders from email and messaging channels

Adds the review queue every inbound message lands in, the channel links that
bind a chat to a business, and the per-business inbox token that routes mail.

Revision ID: 0006_inbound
Revises: 0005_alert_source
Create Date: 2026-09-13
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_inbound"
down_revision: str | None = "0005_alert_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def upgrade() -> None:
    # How an email or a chat finds its way to the right shop.
    op.add_column("businesses", sa.Column("inbox_token", sa.Text(), nullable=True))

    businesses = sa.table("businesses", sa.column("id", UUID), sa.column("inbox_token", sa.Text()))
    connection = op.get_bind()
    for (business_id,) in connection.execute(sa.select(businesses.c.id)).fetchall():
        connection.execute(
            businesses.update()
            .where(businesses.c.id == business_id)
            .values(inbox_token=secrets.token_hex(8))
        )
    op.alter_column("businesses", "inbox_token", nullable=False)
    op.create_unique_constraint("uq_businesses_inbox_token", "businesses", ["inbox_token"])

    op.create_table(
        "inbound_messages",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column(
            "business_id", UUID, sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), nullable=False, server_default=""),
        sa.Column("sender_name", sa.Text()),
        sa.Column("subject", sa.Text()),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("draft", postgresql.JSONB()),
        sa.Column("note", sa.Text()),
        sa.Column("handled_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("handled_at", sa.DateTime()),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=NOW),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
        sa.UniqueConstraint("channel", "external_id", name="uq_inbound_channel_external"),
    )
    # The Inbox lists one business's queue, newest first, usually filtered to
    # what is still pending.
    op.create_index(
        "ix_inbound_business_status",
        "inbound_messages",
        ["business_id", "status", sa.text("received_at DESC")],
    )

    op.create_table(
        "channel_links",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column(
            "business_id", UUID, sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text()),
        sa.Column("linked_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
        sa.UniqueConstraint("channel", "external_id", name="uq_channel_link_external"),
    )
    op.create_index("ix_channel_links_business", "channel_links", ["business_id", "channel"])


def downgrade() -> None:
    op.drop_index("ix_channel_links_business", table_name="channel_links")
    op.drop_table("channel_links")
    op.drop_index("ix_inbound_business_status", table_name="inbound_messages")
    op.drop_table("inbound_messages")
    op.drop_constraint("uq_businesses_inbox_token", "businesses", type_="unique")
    op.drop_column("businesses", "inbox_token")
