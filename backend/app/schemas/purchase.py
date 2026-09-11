"""Purchase request payloads."""

from __future__ import annotations

from .common import DocumentInput, DocumentTotals


class PurchaseInput(DocumentInput):
    """A purchase to record. `partyId` is the supplier."""


class PurchaseTotals(DocumentTotals):
    """Money breakdown for a purchase."""
