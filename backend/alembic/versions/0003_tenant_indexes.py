"""Indexes on the tenant and foreign-key columns

Postgres does not index a foreign key for you, so every query scoped to one
business — which is every query in the app — was a sequential scan over the
whole table. Each index below matches a real access path: the leading column is
the filter, the trailing one the sort or the join, so the planner can satisfy
both from the index.

Revision ID: 0003_indexes
Revises: 0002_rbac
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_indexes"
down_revision: str | None = "0002_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (name, table, columns) — the tenant filter plus how the endpoint orders.
INDEXES: tuple[tuple[str, str, list], ...] = (
    # Document lists, newest first.
    ("ix_sales_business_date", "sales", ["business_id", sa.text("date DESC")]),
    ("ix_purchases_business_date", "purchases", ["business_id", sa.text("date DESC")]),
    ("ix_expenses_business_date", "expenses", ["business_id", sa.text("date DESC")]),
    # Catalogue, ordered by name.
    ("ix_products_business_name", "products", ["business_id", "name"]),
    ("ix_parties_business_name", "parties", ["business_id", "name"]),
    # Recent activity feeds.
    (
        "ix_stock_movements_business_created",
        "stock_movements",
        ["business_id", sa.text("created_at DESC")],
    ),
    (
        "ix_workflow_executions_business_created",
        "workflow_executions",
        ["business_id", sa.text("created_at DESC")],
    ),
    # The outbox monitor filters by business first; the existing
    # (status, created_at) index only helps the worker's own claim query.
    ("ix_events_business_created", "events", ["business_id", sa.text("created_at DESC")]),
    (
        "ix_notifications_business_created",
        "notifications",
        ["business_id", sa.text("created_at DESC")],
    ),
    # Line items are always fetched by their parent document.
    ("ix_sale_items_sale", "sale_items", ["sale_id"]),
    ("ix_purchase_items_purchase", "purchase_items", ["purchase_id"]),
    # The team page, and the per-business member counts on the platform view.
    ("ix_users_business", "users", ["business_id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
