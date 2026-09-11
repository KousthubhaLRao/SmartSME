"""Line-item validation and ownership checks shared by sales and purchases."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Party, Product
from ..schemas import LineInput


def clean_line_items(items: list[LineInput]) -> list[LineInput]:
    """Drop blank/zero lines and validate the rest.

    Quantities must be whole numbers above zero (the column is an integer) and
    prices finite and non-negative, so a stray NaN or negative price can never
    reach the ledger and flip a balance or corrupt a total.
    """
    kept = [i for i in items if (i.description or "").strip() and i.quantity > 0]
    if not kept:
        raise ValueError("Add at least one line item.")
    for i in kept:
        name = i.description.strip()
        if int(i.quantity) != i.quantity or i.quantity <= 0:
            raise ValueError(f'Quantity for "{name}" must be a whole number greater than zero.')
        if i.unitPrice is None or i.unitPrice != i.unitPrice or i.unitPrice < 0:
            raise ValueError(f'Price for "{name}" must be a number of zero or more.')
    return kept


def load_owned_products(
    db: Session, business_id: uuid.UUID, items: list[LineInput]
) -> dict[uuid.UUID, Product]:
    """Load every product referenced by these lines, scoped to the business.

    Raises if any productId belongs to another tenant, which prevents one
    business from moving another's stock through a forged id.
    """
    ids: list[uuid.UUID] = []
    for i in items:
        if not i.productId:
            continue
        try:
            pid = uuid.UUID(i.productId)
        except ValueError as exc:
            raise ValueError("One or more selected products are not available.") from exc
        if pid not in ids:
            ids.append(pid)
    if not ids:
        return {}

    rows = list(
        db.scalars(select(Product).where(Product.business_id == business_id, Product.id.in_(ids)))
    )
    found = {r.id: r for r in rows}
    for pid in ids:
        if pid not in found:
            raise ValueError("One or more selected products are not available.")
    return found


def assert_party_owned(
    db: Session, business_id: uuid.UUID, party_id: str | None
) -> uuid.UUID | None:
    """Verify a customer/supplier belongs to the business, if one was supplied."""
    if not party_id:
        return None
    try:
        pid = uuid.UUID(party_id)
    except ValueError as exc:
        raise ValueError("The selected customer or supplier was not found.") from exc
    exists = db.scalar(select(Party.id).where(Party.id == pid, Party.business_id == business_id))
    if not exists:
        raise ValueError("The selected customer or supplier was not found.")
    return pid
