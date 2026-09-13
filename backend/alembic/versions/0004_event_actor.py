"""Record which user caused each event

Until now an event knew its business but not its author, which was fine while a
business had exactly one account. With employees it is the difference between a
log and an audit trail.

Nullable, and ON DELETE SET NULL: events raised by the seed, by a cron drain or
by a user who has since been removed from the team keep their place in the
history with no author, rather than disappearing with them.

Revision ID: 0004_event_actor
Revises: 0003_indexes
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_event_actor"
down_revision: str | None = "0003_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("events", sa.Column("user_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_events_user", "events", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )
    # "What did this person do" is the question an audit trail gets asked.
    op.create_index("ix_events_user", "events", ["user_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_events_user", table_name="events")
    op.drop_constraint("fk_events_user", "events", type_="foreignkey")
    op.drop_column("events", "user_id")
