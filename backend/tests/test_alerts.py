"""The alert log: filters, dismissal, and where each alert came from.

An alert that says "Low stock: Cooking Oil" is a message. One that also says
which rule fired, on which event, and therefore who caused it, is a log you can
audit — that is what these check.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture(scope="module")
def alerting_rule(client):
    """A rule that raises an alert on every sale, so there is something to read."""
    r = client.post(
        "/api/workflow/rules",
        json={
            "name": "Alert log probe",
            "eventType": "SALE_CREATED",
            "actionType": "notify",
            "actionConfig": {"title": "Sale logged by probe", "severity": "info"},
        },
    )
    assert r.status_code == 201, r.text
    rule = r.json()
    yield rule
    client.delete(f"/api/workflow/rules/{rule['id']}")


def _make_sale(c, workspace, quantity: int = 1):
    r = c.post(
        "/api/sales",
        json={
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": quantity,
                    "unitPrice": 140,
                }
            ],
            "amountPaid": 140 * quantity,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_an_alert_names_the_rule_event_and_person_behind_it(client, workspace, alerting_rule):
    me = client.get("/api/auth/me").json()["user"]
    _make_sale(client, workspace)

    rows = client.get("/api/notifications", params={"pageSize": 50}).json()["rows"]
    mine = next((n for n in rows if n["title"] == "Sale logged by probe"), None)
    assert mine is not None, "the rule should have raised an alert"

    assert mine["source"] is not None
    assert mine["source"]["rule"] == "Alert log probe"
    assert mine["source"]["eventType"] == "SALE_CREATED"
    assert mine["source"]["actor"] == me["name"]
    assert mine["eventId"] and mine["ruleId"]


def test_an_employees_alert_is_attributed_to_the_employee(
    client, employee_client, workspace, alerting_rule
):
    staff = employee_client.get("/api/auth/me").json()["user"]
    # The notify action dedupes against unread alerts of the same title, so
    # clear the decks first or the owner's earlier alert suppresses this one.
    client.post("/api/notifications/read-all")
    _make_sale(employee_client, workspace)

    rows = client.get("/api/notifications", params={"pageSize": 50}).json()["rows"]
    theirs = next(
        (
            n
            for n in rows
            if n["title"] == "Sale logged by probe"
            and (n["source"] or {}).get("actor") == staff["name"]
        ),
        None,
    )
    assert theirs is not None, "the owner should see which employee caused the alert"


def test_severity_counts_and_filtering(client, workspace, alerting_rule):
    _make_sale(client, workspace)
    body = client.get("/api/notifications").json()
    assert [s["value"] for s in body["severities"]] == ["info", "warning", "error"]
    assert sum(s["count"] for s in body["severities"]) >= len(body["rows"])

    only_info = client.get("/api/notifications", params={"severity": "info", "pageSize": 100})
    assert only_info.status_code == 200
    assert all(n["severity"] == "info" for n in only_info.json()["rows"])


def test_an_unknown_severity_is_rejected(client):
    assert client.get("/api/notifications", params={"severity": "urgent"}).status_code == 400


def test_the_unread_filter_only_returns_outstanding_alerts(client, workspace, alerting_rule):
    _make_sale(client, workspace)
    rows = client.get("/api/notifications", params={"unread": True, "pageSize": 100}).json()["rows"]
    assert rows, "there should be something outstanding"
    assert all(n["read"] is False for n in rows)

    client.post(f"/api/notifications/{rows[0]['id']}/read")
    after = client.get("/api/notifications", params={"unread": True, "pageSize": 100}).json()
    assert rows[0]["id"] not in {n["id"] for n in after["rows"]}


def test_an_alert_can_be_put_back(client, workspace, alerting_rule):
    """Cleared by accident, before it was dealt with."""
    _make_sale(client, workspace)
    row = client.get("/api/notifications", params={"unread": True}).json()["rows"][0]

    assert client.post(f"/api/notifications/{row['id']}/read").status_code == 200
    assert client.post(f"/api/notifications/{row['id']}/unread").status_code == 200

    again = client.get("/api/notifications", params={"unread": True, "pageSize": 100}).json()
    assert row["id"] in {n["id"] for n in again["rows"]}


def test_an_alert_can_be_dismissed(client, workspace, alerting_rule):
    _make_sale(client, workspace)
    row = client.get("/api/notifications", params={"pageSize": 10}).json()["rows"][0]

    assert client.delete(f"/api/notifications/{row['id']}").status_code == 200
    remaining = client.get("/api/notifications", params={"pageSize": 200}).json()["rows"]
    assert row["id"] not in {n["id"] for n in remaining}

    assert client.delete(f"/api/notifications/{uuid.uuid4()}").status_code == 404
    assert client.post(f"/api/notifications/{uuid.uuid4()}/unread").status_code == 404


def test_clearing_read_alerts_leaves_the_outstanding_ones(client, workspace, alerting_rule):
    _make_sale(client, workspace)
    _make_sale(client, workspace)

    rows = client.get("/api/notifications", params={"unread": True, "pageSize": 200}).json()["rows"]
    assert len(rows) >= 1
    client.post(f"/api/notifications/{rows[0]['id']}/read")

    cleared = client.post("/api/notifications/clear-read")
    assert cleared.status_code == 200
    assert cleared.json()["removed"] >= 1

    left = client.get("/api/notifications", params={"pageSize": 200}).json()["rows"]
    assert all(n["read"] is False for n in left), "only outstanding alerts should remain"


def test_an_alert_with_no_source_still_serializes(client):
    """Alerts predating the source columns, and any raised outside a rule."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import Business, Notification

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        db.add(
            Notification(
                business_id=business_id,
                type="workflow",
                severity="warning",
                title="Sourceless alert",
                message="Raised without a rule.",
            )
        )
        db.commit()

    rows = client.get("/api/notifications", params={"pageSize": 200}).json()["rows"]
    orphan = next(n for n in rows if n["title"] == "Sourceless alert")
    assert orphan["source"] is None
    assert orphan["eventId"] is None and orphan["ruleId"] is None
