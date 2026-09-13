"""Who caused each event.

An event's author is what turns the outbox from a log into an audit trail, and
the interesting case is the chained one: a sale raises SALE_CREATED, processing
that raises STOCK_UPDATED, and both have to point at the person who made the
sale rather than at nobody.
"""

from __future__ import annotations

import uuid


def _events(client, **params) -> list[dict]:
    body = client.get("/api/events", params={"pageSize": 200, **params}).json()
    return body["rows"]


def _find(rows: list[dict], type_: str, ref_key: str, ref_id: str) -> dict | None:
    for row in rows:
        if row["type"] == type_ and str(row["payload"].get(ref_key)) == ref_id:
            return row
    return None


def test_a_sale_records_who_made_it(client, workspace):
    me = client.get("/api/auth/me").json()["user"]
    sale = client.post(
        "/api/sales",
        json={
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 1,
                    "unitPrice": 140,
                }
            ],
            "amountPaid": 140,
        },
    )
    assert sale.status_code == 201, sale.text
    sale_id = sale.json()["id"]

    created = _find(_events(client), "SALE_CREATED", "saleId", sale_id)
    assert created is not None, "the sale should have raised an event"
    assert created["actor"] == me["name"]


def test_a_chained_event_inherits_the_same_author(client, workspace):
    """The stock movement is raised by the worker, not by the request, so it can
    only know the author by inheriting it from the event it came from."""
    me = client.get("/api/auth/me").json()["user"]
    sale_id = client.post(
        "/api/sales",
        json={
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 2,
                    "unitPrice": 140,
                }
            ],
            "amountPaid": 280,
        },
    ).json()["id"]

    rows = _events(client)
    stock = next(
        (
            r
            for r in rows
            if r["type"] == "STOCK_UPDATED" and str(r["payload"].get("refId")) == sale_id
        ),
        None,
    )
    assert stock is not None, "the sale should have chained a stock event"
    assert stock["actor"] == me["name"]


def test_an_employees_work_is_attributed_to_them_not_the_owner(employee_client, client):
    """The whole point of the column: two people, one business."""
    staff = employee_client.get("/api/auth/me").json()["user"]
    owner = client.get("/api/auth/me").json()["user"]
    assert staff["name"] != owner["name"]

    expense = employee_client.post(
        "/api/expenses", json={"description": "Counter float", "amount": 500}
    )
    assert expense.status_code == 201, expense.text
    expense_id = expense.json()["id"]

    # The owner reads the log and sees who did it.
    logged = _find(_events(client), "EXPENSE_ADDED", "expenseId", expense_id)
    assert logged is not None
    assert logged["actor"] == staff["name"]


def test_purchases_and_stock_adjustments_are_attributed(client, workspace):
    me = client.get("/api/auth/me").json()["user"]

    purchase_id = client.post(
        "/api/purchases",
        json={
            "partyId": workspace["supplierId"],
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 5,
                    "unitPrice": 100,
                }
            ],
            "amountPaid": 500,
        },
    ).json()["id"]

    adjusted = client.post(
        f"/api/products/{workspace['productId']}/adjust",
        json={"delta": -1, "note": "spillage"},
    )
    assert adjusted.status_code == 200

    rows = _events(client)
    assert _find(rows, "PURCHASE_CREATED", "purchaseId", purchase_id)["actor"] == me["name"]

    adjustment = next(
        (
            r
            for r in rows
            if r["type"] == "STOCK_UPDATED" and r["payload"].get("cause") == "adjustment"
        ),
        None,
    )
    assert adjustment is not None
    assert adjustment["actor"] == me["name"]


def test_smart_input_attributes_the_publisher(client):
    me = client.get("/api/auth/me").json()["user"]
    published = client.post(
        "/api/input/publish",
        json={
            "type": "expense",
            "category": "Transport",
            "description": "Auto fare",
            "amount": 120,
            "source": "nlp",
        },
    )
    assert published.status_code == 200, published.text

    rows = _events(client, status="done")
    logged = next(
        (r for r in rows if r["type"] == "EXPENSE_ADDED" and r["actor"] == me["name"]), None
    )
    assert logged is not None, "a published draft should carry its author"


def test_events_without_an_author_still_serialize(client):
    """Seeded and system events have no user, and must not break the page."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import Business, Event

    business_id = uuid.UUID(client.get("/api/auth/me").json()["business"]["id"])
    with SessionLocal() as db:
        assert db.scalar(select(Business).where(Business.id == business_id))
        db.add(
            Event(
                business_id=business_id,
                user_id=None,
                type="ORDER_CREATED",
                payload={"note": "raised by the system"},
                status="done",
            )
        )
        db.commit()

    orphan = next((r for r in _events(client) if r["type"] == "ORDER_CREATED"), None)
    assert orphan is not None
    assert orphan["actor"] is None
