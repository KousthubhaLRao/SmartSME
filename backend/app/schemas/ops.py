"""Workflow rules and business settings."""

from __future__ import annotations

from pydantic import BaseModel


class RuleInput(BaseModel):
    """A WHEN/THEN automation rule.

    The three `condition*` fields are all optional together: a rule with no
    condition fires on every event of its type.
    """

    name: str
    eventType: str
    conditionField: str | None = None
    conditionOp: str | None = None
    conditionValue: str | None = None
    actionType: str = "notify"
    actionConfig: dict = {}
    enabled: bool = True


class SettingsInput(BaseModel):
    """Business profile, as shown on invoices and reports."""

    name: str
    gstNumber: str | None = None
    panNumber: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    currency: str = "INR"
    taxRate: float = 18
    invoicePrefix: str = "INV"
