"""Record when an event was claimed, and scope inbound dedup to a business

Two corrections.

`events.claimed_at` exists because the outbox sweep had no way to tell a worker
that died from one that is still working: it compared `created_at`, which says
when the event was *published*. Under the exact conditions the sweep is for - a
broker outage, then a backlog draining - every event is old, so the sweep was
releasing rows a live worker held and handing them to a second worker.

The inbound unique constraint gains `business_id`. One supplier mailing the same
order to two shops produces one `Message-ID`; a global constraint meant only the
first shop ever saw it.

Revision ID: 0007_claimed_at
Revises: 0006_inbound
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_claimed_at"
down_revision: str | None = "0006_inbound"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("claimed_at", sa.DateTime(), nullable=True))
    # Anything already mid-flight gets a claim time now, so the sweep does not
    # treat rows that predate this column as abandoned the moment it runs.
    op.execute("update events set claimed_at = now() where status = 'processing'")
    # The sweep looks for old claims; this is the index it reads.
    op.create_index("ix_events_claimed", "events", ["status", "claimed_at"])

    op.drop_constraint("uq_inbound_channel_external", "inbound_messages", type_="unique")
    op.create_unique_constraint(
        "uq_inbound_business_channel_external",
        "inbound_messages",
        ["business_id", "channel", "external_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_inbound_business_channel_external", "inbound_messages", type_="unique"
    )
    op.create_unique_constraint(
        "uq_inbound_channel_external", "inbound_messages", ["channel", "external_id"]
    )
    op.drop_index("ix_events_claimed", table_name="events")
    op.drop_column("events", "claimed_at")
