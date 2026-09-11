"""The event bus, used as a transactional outbox.

`publish` takes the *same* Session as the business write, so an event can never
be emitted for a change that rolled back, nor lost for one that committed.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from .models import Event

EVENT_TYPES = (
    "SALE_CREATED",
    "PURCHASE_CREATED",
    "STOCK_UPDATED",
    "EXPENSE_ADDED",
    "PAYMENT_RECEIVED",
    "ORDER_CREATED",
)

EVENT_LABELS = {
    "SALE_CREATED": "Sale created",
    "PURCHASE_CREATED": "Purchase created",
    "STOCK_UPDATED": "Stock updated",
    "EXPENSE_ADDED": "Expense added",
    "PAYMENT_RECEIVED": "Payment received",
    "ORDER_CREATED": "Order created",
}


def publish(db: Session, business_id: uuid.UUID, type_: str, payload: dict) -> Event:
    """Append an event inside the caller's transaction (do not commit here)."""
    event = Event(business_id=business_id, type=type_, payload=payload, status="pending")
    db.add(event)
    return event
