"""Initial SmartSME schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def _id() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True, nullable=False)


def _business_fk() -> sa.Column:
    return sa.Column(
        "business_id",
        UUID,
        sa.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )


def _money(name: str, default: str = "0") -> sa.Column:
    return sa.Column(name, sa.Float(), nullable=False, server_default=sa.text(default))


def upgrade() -> None:
    op.create_table(
        "businesses",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("gst_number", sa.Text()),
        sa.Column("pan_number", sa.Text()),
        sa.Column("address", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("email", sa.Text()),
        sa.Column("currency", sa.Text(), nullable=False, server_default="INR"),
        _money("tax_rate", "18"),
        sa.Column("invoice_prefix", sa.Text(), nullable=False, server_default="INV"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )

    op.create_table(
        "users",
        _id(),
        _business_fk(),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )

    op.create_table(
        "parties",
        _id(),
        _business_fk(),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text()),
        sa.Column("email", sa.Text()),
        sa.Column("gst_number", sa.Text()),
        sa.Column("address", sa.Text()),
        _money("balance"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )

    op.create_table(
        "products",
        _id(),
        _business_fk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sku", sa.Text()),
        sa.Column("hsn", sa.Text()),
        sa.Column("unit", sa.Text(), nullable=False, server_default="pcs"),
        _money("purchase_price"),
        _money("selling_price"),
        sa.Column("stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )

    op.create_table(
        "stock_movements",
        _id(),
        _business_fk(),
        sa.Column("product_id", UUID, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ref_type", sa.Text()),
        sa.Column("ref_id", UUID),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )

    for table, ref_col in (("sales", "invoice_number"), ("purchases", "reference_number")):
        op.create_table(
            table,
            _id(),
            _business_fk(),
            sa.Column("party_id", UUID, sa.ForeignKey("parties.id", ondelete="SET NULL")),
            sa.Column(ref_col, sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="completed"),
            _money("subtotal"),
            sa.Column("discount_type", sa.Text(), nullable=False, server_default="none"),
            _money("discount_value"),
            _money("discount_amount"),
            _money("tax"),
            _money("total"),
            _money("amount_paid"),
            sa.Column("payment_status", sa.Text(), nullable=False, server_default="unpaid"),
            sa.Column("source", sa.Text(), nullable=False, server_default="form"),
            sa.Column("notes", sa.Text()),
            sa.Column("date", sa.DateTime(), nullable=False, server_default=NOW),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
        )

    for table, parent, parent_col in (
        ("sale_items", "sales", "sale_id"),
        ("purchase_items", "purchases", "purchase_id"),
    ):
        op.create_table(
            table,
            _id(),
            sa.Column(parent_col, UUID, sa.ForeignKey(f"{parent}.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", UUID, sa.ForeignKey("products.id", ondelete="SET NULL")),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
            _money("unit_price"),
            _money("line_total"),
        )

    op.create_table(
        "expenses",
        _id(),
        _business_fk(),
        sa.Column("category", sa.Text(), nullable=False, server_default="General"),
        sa.Column("description", sa.Text(), nullable=False),
        _money("amount"),
        sa.Column("flagged", sa.Text()),
        sa.Column("date", sa.DateTime(), nullable=False, server_default=NOW),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )

    op.create_table(
        "events",
        _id(),
        _business_fk(),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
        sa.Column("processed_at", sa.DateTime()),
    )
    # The worker polls pending events oldest-first on every tick.
    op.create_index("ix_events_status_created_at", "events", ["status", "created_at"])

    op.create_table(
        "workflow_rules",
        _id(),
        _business_fk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("condition_field", sa.Text()),
        sa.Column("condition_op", sa.Text()),
        sa.Column("condition_value", sa.Text()),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("action_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("built_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )
    # Rule lookup per event type happens for every processed event.
    op.create_index(
        "ix_workflow_rules_lookup", "workflow_rules", ["business_id", "event_type", "enabled"]
    )

    op.create_table(
        "workflow_executions",
        _id(),
        _business_fk(),
        sa.Column("rule_id", UUID, sa.ForeignKey("workflow_rules.id", ondelete="SET NULL")),
        sa.Column("rule_name", sa.Text(), nullable=False),
        sa.Column("event_id", UUID, sa.ForeignKey("events.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )

    op.create_table(
        "notifications",
        _id(),
        _business_fk(),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="info"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=NOW),
    )
    # The bell badge counts unread rows on every page load.
    op.create_index("ix_notifications_unread", "notifications", ["business_id", "read"])


def downgrade() -> None:
    for index, table in (
        ("ix_notifications_unread", "notifications"),
        ("ix_workflow_rules_lookup", "workflow_rules"),
        ("ix_events_status_created_at", "events"),
    ):
        op.drop_index(index, table_name=table)
    for table in (
        "notifications",
        "workflow_executions",
        "workflow_rules",
        "events",
        "expenses",
        "purchase_items",
        "sale_items",
        "purchases",
        "sales",
        "stock_movements",
        "products",
        "parties",
        "users",
        "businesses",
    ):
        op.drop_table(table)
