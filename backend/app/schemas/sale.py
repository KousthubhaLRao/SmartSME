"""Sale request payloads."""

from __future__ import annotations

from .common import DocumentInput, DocumentTotals


class SaleInput(DocumentInput):
    """A sale to record. `partyId` is the customer; omit it for a walk-in."""


class SaleTotals(DocumentTotals):
    """Money breakdown for a sale."""
