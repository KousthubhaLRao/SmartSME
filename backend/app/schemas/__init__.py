"""Pydantic request payloads — the wire contract with the React client.

Grouped to mirror `app.models`. These validate what comes in; responses are
assembled by `app.serializers`.
"""

from .auth import AcceptInviteInput, InviteInput, SignInInput, SignUpInput
from .catalog import ExpenseInput, PartyInput, ProductInput, StockAdjustInput
from .common import (
    BusinessDate,
    DateInput,
    DocumentInput,
    DocumentTotals,
    LineInput,
    PaymentInput,
    SettleResult,
)
from .ops import RuleInput, SettingsInput
from .purchase import PurchaseInput, PurchaseTotals
from .sale import SaleInput, SaleTotals
from .smart_input import ParseTextInput

__all__ = [
    "AcceptInviteInput",
    "BusinessDate",
    "DateInput",
    "DocumentInput",
    "DocumentTotals",
    "ExpenseInput",
    "InviteInput",
    "LineInput",
    "ParseTextInput",
    "PartyInput",
    "PaymentInput",
    "ProductInput",
    "PurchaseInput",
    "PurchaseTotals",
    "RuleInput",
    "SaleInput",
    "SaleTotals",
    "SettingsInput",
    "SettleResult",
    "SignInInput",
    "SignUpInput",
    "StockAdjustInput",
]
