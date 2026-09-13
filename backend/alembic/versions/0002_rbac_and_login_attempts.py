"""RBAC, team invites and login attempt throttling

Revision ID: 0002_rbac
Revises: 0001_initial
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_rbac"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def upgrade() -> None:
    # Superusers and admins belong to no business.
    op.alter_column("users", "business_id", existing_type=UUID, nullable=True)

    op.create_table(
        "invites",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column(
            "business_id",
            UUID,
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="employee"),
        # Only the hash is stored; the token itself is shown once, at creation.
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("invited_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime()),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )
    op.create_index("ix_invites_business", "invites", ["business_id", "created_at"])

    op.create_table(
        "login_attempts",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text()),
        sa.Column("successful", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )
    # The lockout check reads the most recent attempts for one email, and the
    # sweep deletes old rows; both are covered here.
    op.create_index("ix_login_attempts_email", "login_attempts", ["email", "created_at"])
    op.create_index("ix_login_attempts_ip", "login_attempts", ["ip", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempts_ip", table_name="login_attempts")
    op.drop_index("ix_login_attempts_email", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_invites_business", table_name="invites")
    op.drop_table("invites")
    # Rows with a null business_id would block this; they are platform accounts
    # and have to be removed before the column can be made required again.
    op.execute("delete from users where business_id is null")
    op.alter_column("users", "business_id", existing_type=UUID, nullable=False)
