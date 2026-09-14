"""Link each alert back to the rule and event that raised it

An alert that says "Low stock: Cooking Oil" is useful; one that also says which
rule fired, on which event, and therefore who caused it, is an alert *log*. Both
columns are nullable and SET NULL on delete, so deleting a rule blunts the
history rather than erasing it.

Revision ID: 0005_alert_source
Revises: 0004_event_actor
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_alert_source"
down_revision: str | None = "0004_event_actor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("notifications", sa.Column("event_id", UUID, nullable=True))
    op.add_column("notifications", sa.Column("rule_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_notifications_event", "notifications", "events", ["event_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_notifications_rule",
        "notifications",
        "workflow_rules",
        ["rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # The alert list filters on severity and orders by time.
    op.create_index(
        "ix_notifications_severity",
        "notifications",
        ["business_id", "severity", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_severity", table_name="notifications")
    op.drop_constraint("fk_notifications_rule", "notifications", type_="foreignkey")
    op.drop_constraint("fk_notifications_event", "notifications", type_="foreignkey")
    op.drop_column("notifications", "rule_id")
    op.drop_column("notifications", "event_id")
