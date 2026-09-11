"""Configurable WHEN/THEN rules and the audit trail of their evaluations.

Core effects (inventory, balances) are applied unconditionally by the worker;
these rules only add the optional behaviour on top, which is why disabling one
can never corrupt the books.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, fk, pk, timestamp


class WorkflowRule(Base):
    __tablename__ = "workflow_rules"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    condition_field: Mapped[str | None] = mapped_column(Text)
    condition_op: Mapped[str | None] = mapped_column(Text)
    condition_value: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    action_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Seeded rules; shown to the user but flagged as part of the default set.
    built_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = timestamp()


class WorkflowExecution(Base):
    """One row per rule evaluation, matched or not, so the engine is auditable."""

    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    rule_id: Mapped[uuid.UUID | None] = fk("workflow_rules.id", ondelete="SET NULL", nullable=True)
    #: Kept denormalised so the history survives the rule being deleted.
    rule_name: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[uuid.UUID | None] = fk("events.id", ondelete="SET NULL", nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # matched | skipped | error
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp()
