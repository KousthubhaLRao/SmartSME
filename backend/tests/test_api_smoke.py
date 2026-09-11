"""Smoke tests across every functional endpoint.

One pass over the whole HTTP surface: each route is called the way the SPA calls
it, and the response is checked for the shape the client relies on. This is not a
substitute for the unit tests in `test_domain.py` — the arithmetic lives there —
it is the "does the wiring hold end to end" layer: routing, auth, serialization,
the domain call behind each route, and the event effects that follow a write.

These tests share one business, built once per session, and run in file order.
"""

from __future__ import annotations

import base64
import uuid

import pytest

# A 1x1 transparent PNG — enough to exercise the upload path.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


# ---------------------------------------------------------------------------
# Meta and auth
# ---------------------------------------------------------------------------
def test_health_needs_no_session(anon):
    r = anon.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "service": "smartsme-api"}


@pytest.mark.parametrize(
    "path",
    ["/api/dashboard", "/api/sales", "/api/products", "/api/parties", "/api/settings"],
)
def test_protected_routes_reject_anonymous_callers(fresh_client, path):
    assert fresh_client.get(path).status_code == 401


def test_auth_lifecycle(fresh_client):
    email = f"lifecycle-{uuid.uuid4().hex[:12]}@smoketest.dev"
    password = "smoke1234"

    created = fresh_client.post(
        "/api/auth/sign-up",
        json={
            "businessName": "Lifecycle Traders",
            "name": "Lifecycle Owner",
            "email": email,
            "password": password,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["business"]["name"] == "Lifecycle Traders"

    me = fresh_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email

    assert fresh_client.post("/api/auth/sign-out").status_code == 200
    assert fresh_client.get("/api/auth/me").status_code == 401

    back = fresh_client.post("/api/auth/sign-in", json={"email": email, "password": password})
    assert back.status_code == 200
    assert back.json()["user"]["email"] == email

    wrong = fresh_client.post(
        "/api/auth/sign-in", json={"email": email, "password": "not-the-password"}
    )
    assert wrong.status_code == 401


def test_sign_up_rejects_a_duplicate_email(fresh_client):
    email = f"dupe-{uuid.uuid4().hex[:12]}@smoketest.dev"
    body = {
        "businessName": "First Traders",
        "name": "First Owner",
        "email": email,
        "password": "smoke1234",
    }
    assert fresh_client.post("/api/auth/sign-up", json=body).status_code == 201
    assert fresh_client.post("/api/auth/sign-up", json=body).status_code in (400, 409)


# ---------------------------------------------------------------------------
# Catalogue: products, parties, expenses
# ---------------------------------------------------------------------------
def test_product_crud_and_stock_adjustment(client, workspace):
    listing = client.get("/api/products")
    assert listing.status_code == 200
    body = listing.json()
    assert {"rows", "movements", "stats", "currency"} <= body.keys()
    assert any(p["id"] == workspace["productId"] for p in body["rows"])

    created = client.post(
        "/api/products",
        json={"name": "Basmati Rice", "unit": "kg", "sellingPrice": 90, "stock": 20},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    updated = client.put(
        f"/api/products/{pid}",
        json={"name": "Basmati Rice 5kg", "unit": "kg", "sellingPrice": 420, "stock": 20},
    )
    assert updated.status_code == 200

    adjusted = client.post(f"/api/products/{pid}/adjust", json={"delta": -5, "note": "damaged"})
    assert adjusted.status_code == 200

    rows = {p["id"]: p for p in client.get("/api/products").json()["rows"]}
    assert rows[pid]["stock"] == 15
    assert rows[pid]["name"] == "Basmati Rice 5kg"

    assert client.delete(f"/api/products/{pid}").status_code == 200
    assert pid not in {p["id"] for p in client.get("/api/products").json()["rows"]}


def test_party_crud(client, workspace):
    listing = client.get("/api/parties")
    assert listing.status_code == 200
    assert any(p["id"] == workspace["customerId"] for p in listing.json()["rows"])

    created = client.post("/api/parties", json={"type": "customer", "name": "Temp Buyer"})
    assert created.status_code == 201
    party_id = created.json()["id"]

    renamed = client.put(
        f"/api/parties/{party_id}", json={"type": "customer", "name": "Temp Buyer Renamed"}
    )
    assert renamed.status_code == 200
    assert client.delete(f"/api/parties/{party_id}").status_code == 200


def test_expense_crud_and_totals(client):
    created = client.post(
        "/api/expenses",
        json={"category": "Utilities", "description": "Shop electricity", "amount": 1200},
    )
    assert created.status_code == 201, created.text
    expense_id = created.json()["id"]

    listing = client.get("/api/expenses")
    assert listing.status_code == 200
    body = listing.json()
    assert body["stats"]["total"] >= 1200
    assert any(e["id"] == expense_id for e in body["rows"])
    assert any(c["label"] == "Utilities" for c in body["byCategory"])

    assert client.delete(f"/api/expenses/{expense_id}").status_code == 200
    assert expense_id not in {e["id"] for e in client.get("/api/expenses").json()["rows"]}


# ---------------------------------------------------------------------------
# Sales and purchases
# ---------------------------------------------------------------------------
def _stock_of(client, product_id: str) -> int:
    rows = {p["id"]: p for p in client.get("/api/products").json()["rows"]}
    return rows[product_id]["stock"]


def test_sale_flow_moves_stock_and_records_payment(client, workspace):
    opening_stock = _stock_of(client, workspace["productId"])

    created = client.post(
        "/api/sales",
        json={
            "partyId": workspace["customerId"],
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 2,
                    "unitPrice": 140,
                }
            ],
            "amountPaid": 0,
        },
    )
    assert created.status_code == 201, created.text
    sale_id = created.json()["id"]
    assert created.json()["invoiceNumber"].startswith("INV-")

    detail = client.get(f"/api/sales/{sale_id}")
    assert detail.status_code == 200
    assert detail.json()["paymentStatus"] == "unpaid"
    total = detail.json()["total"]

    # The sale publishes SALE_CREATED, and the event chain turns that into a
    # stock movement before the request returns.
    assert _stock_of(client, workspace["productId"]) == opening_stock - 2

    assert client.post(f"/api/sales/{sale_id}/payment", json={"amount": total}).status_code == 200
    assert client.get(f"/api/sales/{sale_id}").json()["paymentStatus"] == "paid"

    dated = client.patch(f"/api/sales/{sale_id}/date", json={"date": "2026-09-01"})
    assert dated.status_code == 200
    assert client.get(f"/api/sales/{sale_id}").json()["date"].startswith("2026-09-01")

    listing = client.get("/api/sales")
    assert listing.status_code == 200
    assert {"rows", "stats", "currency"} <= listing.json().keys()
    assert any(s["id"] == sale_id for s in listing.json()["rows"])


def test_cancelling_a_sale_returns_the_stock(client, workspace):
    opening_stock = _stock_of(client, workspace["productId"])

    sale_id = client.post(
        "/api/sales",
        json={
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 3,
                    "unitPrice": 140,
                }
            ],
            "amountPaid": 0,
        },
    ).json()["id"]

    assert client.post(f"/api/sales/{sale_id}/cancel").status_code == 200
    assert client.get(f"/api/sales/{sale_id}").json()["status"] == "cancelled"
    assert _stock_of(client, workspace["productId"]) == opening_stock


def test_sale_requires_at_least_one_line(client, workspace):
    r = client.post("/api/sales", json={"partyId": workspace["customerId"], "items": []})
    assert r.status_code == 400


def test_missing_sale_is_a_404(client):
    assert client.get(f"/api/sales/{uuid.uuid4()}").status_code == 404


def test_purchase_flow_adds_stock_and_records_payment(client, workspace):
    opening_stock = _stock_of(client, workspace["productId"])

    created = client.post(
        "/api/purchases",
        json={
            "partyId": workspace["supplierId"],
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 10,
                    "unitPrice": 100,
                }
            ],
            "amountPaid": 0,
        },
    )
    assert created.status_code == 201, created.text
    purchase_id = created.json()["id"]
    assert created.json()["referenceNumber"].startswith("PO-")

    detail = client.get(f"/api/purchases/{purchase_id}")
    assert detail.status_code == 200
    total = detail.json()["total"]

    assert _stock_of(client, workspace["productId"]) == opening_stock + 10

    paid = client.post(f"/api/purchases/{purchase_id}/payment", json={"amount": total})
    assert paid.status_code == 200
    assert client.get(f"/api/purchases/{purchase_id}").json()["paymentStatus"] == "paid"

    dated = client.patch(f"/api/purchases/{purchase_id}/date", json={"date": "2026-09-02"})
    assert dated.status_code == 200

    listing = client.get("/api/purchases")
    assert listing.status_code == 200
    assert any(p["id"] == purchase_id for p in listing.json()["rows"])


def test_cancelling_a_purchase_removes_the_stock(client, workspace):
    opening_stock = _stock_of(client, workspace["productId"])

    purchase_id = client.post(
        "/api/purchases",
        json={
            "partyId": workspace["supplierId"],
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 4,
                    "unitPrice": 100,
                }
            ],
            "amountPaid": 0,
        },
    ).json()["id"]

    assert client.post(f"/api/purchases/{purchase_id}/cancel").status_code == 200
    assert _stock_of(client, workspace["productId"]) == opening_stock


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------
def test_settling_one_party_and_then_everything(client, workspace):
    def unpaid_sale() -> None:
        r = client.post(
            "/api/sales",
            json={
                "partyId": workspace["customerId"],
                "items": [
                    {
                        "productId": workspace["productId"],
                        "description": "Cooking Oil",
                        "quantity": 1,
                        "unitPrice": 140,
                    }
                ],
                "amountPaid": 0,
            },
        )
        assert r.status_code == 201, r.text

    unpaid_sale()
    settled = client.post(f"/api/parties/{workspace['customerId']}/settle")
    assert settled.status_code == 200
    assert settled.json()["count"] >= 1
    assert settled.json()["total"] > 0

    unpaid_sale()
    all_settled = client.post("/api/parties/settle-all/receivable")
    assert all_settled.status_code == 200
    assert all_settled.json()["count"] >= 1

    assert client.post("/api/parties/settle-all/payable").status_code == 200
    assert client.post("/api/parties/settle-all/nonsense").status_code == 400


# ---------------------------------------------------------------------------
# Smart Input
# ---------------------------------------------------------------------------
def test_smart_input_status_lists_the_catalogue(client, workspace):
    r = client.get("/api/input/status")
    assert r.status_code == 200
    body = r.json()
    # No API key is configured for the tests, so the built-in parser is in play.
    assert body["hasAI"] is False
    assert body["hasVision"] is False
    assert any(p["id"] == workspace["customerId"] for p in body["parties"])
    assert any(p["id"] == workspace["productId"] for p in body["products"])


def test_parse_text_falls_back_to_the_built_in_parser(client, workspace):
    r = client.post(
        "/api/input/parse-text", json={"text": "sold 2 Cooking Oil to Anita Stores for 280"}
    )
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["engine"] == "Heuristic"
    assert draft["suggestedType"] == "sale"
    # Grounding: the free text is resolved against this business's catalogue.
    assert draft["partyId"] == workspace["customerId"]
    assert draft["items"][0]["productId"] == workspace["productId"]
    assert draft["items"][0]["quantity"] == 2


def test_parse_image_reports_ocr_as_unavailable_without_a_key(client):
    r = client.post("/api/input/parse-image", files={"file": ("bill.png", TINY_PNG, "image/png")})
    assert r.status_code == 400
    assert "OCR" in r.json()["detail"]


def test_publishing_a_draft_records_the_transaction(client):
    r = client.post(
        "/api/input/publish",
        json={
            "type": "expense",
            "category": "Transport",
            "description": "Tempo hire",
            "amount": 850,
            "source": "nlp",
        },
    )
    assert r.status_code == 200, r.text
    assert any(e["description"] == "Tempo hire" for e in client.get("/api/expenses").json()["rows"])


# ---------------------------------------------------------------------------
# Workflow, events, notifications
# ---------------------------------------------------------------------------
def test_workflow_rule_crud(client):
    listing = client.get("/api/workflow")
    assert listing.status_code == 200
    body = listing.json()
    assert {"rules", "executions", "eventTypes"} <= body.keys()
    # Sign-up installs the built-in rules.
    assert body["rules"]

    created = client.post(
        "/api/workflow/rules",
        json={
            "name": "Smoke rule",
            "eventType": "SALE_CREATED",
            "actionType": "notify",
            "actionConfig": {"title": "Smoke notification", "severity": "info"},
        },
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    renamed = client.put(
        f"/api/workflow/rules/{rule_id}",
        json={"name": "Smoke rule renamed", "eventType": "SALE_CREATED", "actionType": "notify"},
    )
    assert renamed.status_code == 200

    toggled = client.post(f"/api/workflow/rules/{rule_id}/toggle")
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False

    rejected = client.post("/api/workflow/rules", json={"name": "Bad", "eventType": "NOPE"})
    assert rejected.status_code == 400
    assert client.delete(f"/api/workflow/rules/{rule_id}").status_code == 200


def test_built_in_rules_cannot_be_deleted(client):
    built_in = next(
        (r for r in client.get("/api/workflow").json()["rules"] if r.get("builtIn")), None
    )
    if built_in is None:
        pytest.skip("no built-in rule installed for this business")
    assert client.delete(f"/api/workflow/rules/{built_in['id']}").status_code == 400


def test_event_bus_records_replays_and_drains(client):
    listing = client.get("/api/events")
    assert listing.status_code == 200
    body = listing.json()
    assert {"rows", "counts", "eventTypes"} <= body.keys()
    # Every write so far went through the outbox and was processed inline.
    assert body["counts"]["done"] > 0
    assert body["counts"]["dead"] == 0
    assert any(e["type"] == "SALE_CREATED" for e in body["rows"])

    filtered = client.get("/api/events", params={"status": "done"})
    assert filtered.status_code == 200
    assert all(e["status"] == "done" for e in filtered.json()["rows"])

    event_id = body["rows"][0]["id"]
    assert client.post(f"/api/events/{event_id}/replay").status_code == 200
    assert client.post(f"/api/events/{uuid.uuid4()}/replay").status_code == 404

    drained = client.post("/api/events/drain")
    assert drained.status_code == 200
    assert "processed" in drained.json()


def test_notifications_can_be_read_one_by_one_and_in_bulk(client, workspace):
    rule = client.post(
        "/api/workflow/rules",
        json={
            "name": "Notify on every sale",
            "eventType": "SALE_CREATED",
            "actionType": "notify",
            "actionConfig": {"title": "Sale logged", "severity": "info"},
        },
    )
    assert rule.status_code == 201

    client.post(
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

    listing = client.get("/api/notifications")
    assert listing.status_code == 200
    rows = listing.json()["rows"]
    assert rows, "the workflow rule should have raised a notification"

    assert client.get("/api/notifications/unread-count").status_code == 200
    assert client.post(f"/api/notifications/{rows[0]['id']}/read").status_code == 200
    assert client.post(f"/api/notifications/{uuid.uuid4()}/read").status_code == 404

    assert client.post("/api/notifications/read-all").status_code == 200
    assert client.get("/api/notifications/unread-count").json()["unread"] == 0

    client.delete(f"/api/workflow/rules/{rule.json()['id']}")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_round_trip(client):
    current = client.get("/api/settings")
    assert current.status_code == 200
    assert {"business", "ai"} <= current.json().keys()

    updated = client.put(
        "/api/settings",
        json={
            "name": "Smoke Test Traders",
            "gstNumber": "29ABCDE1234F1Z5",
            "currency": "INR",
            "taxRate": 12,
            "invoicePrefix": "SMK",
        },
    )
    assert updated.status_code == 200
    assert client.get("/api/settings").json()["business"]["taxRate"] == 12

    assert client.put("/api/settings", json={"name": "", "taxRate": 18}).status_code == 400
    assert client.put("/api/settings", json={"name": "Ok", "taxRate": 250}).status_code == 400

    # Put the profile back so the later assertions see the usual values.
    client.put("/api/settings", json={"name": "Smoke Test Traders", "taxRate": 18})


# ---------------------------------------------------------------------------
# Dashboard and reports
# ---------------------------------------------------------------------------
def test_dashboard_aggregates(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert {"recentSales", "recentPurchases", "business"} <= body.keys()
    assert body["business"]["name"] == "Smoke Test Traders"
    assert body["recentSales"]


def test_reports_overview_and_revenue_series(client):
    overview = client.get("/api/reports/overview")
    assert overview.status_code == 200
    assert overview.json()["currency"] == "INR"

    revenue = client.get("/api/reports/revenue", params={"days": 90})
    assert revenue.status_code == 200
    assert revenue.json()["days"] == 90
    # Longer windows are bucketed by week rather than by day.
    assert revenue.json()["points"]
    assert all({"label", "value", "full"} <= p.keys() for p in revenue.json()["points"])

    # An unsupported window falls back to 30 days rather than erroring.
    assert client.get("/api/reports/revenue", params={"days": 4}).json()["days"] == 30


@pytest.mark.parametrize("type_", ["sales", "purchases", "expenses", "consolidated"])
def test_report_preview_for_every_type(client, type_):
    r = client.get("/api/reports/preview", params={"type": type_, "preset": "year"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fileName"].endswith(".pdf")
    assert body["sections"]


def test_report_preview_rejects_unknown_parameters(client):
    assert client.get("/api/reports/preview", params={"type": "nope"}).status_code == 400
    assert client.get("/api/reports/preview", params={"preset": "nope"}).status_code == 400


def test_report_downloads_as_pdf_and_csv(client):
    pdf = client.get(
        "/api/reports/download", params={"type": "consolidated", "preset": "year", "fmt": "pdf"}
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]

    csv = client.get(
        "/api/reports/download", params={"type": "sales", "preset": "year", "fmt": "csv"}
    )
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.strip()


def test_empty_report_period_is_a_404(client):
    r = client.get(
        "/api/reports/download",
        params={"type": "sales", "preset": "custom", "from": "2001-01-01", "to": "2001-01-31"},
    )
    assert r.status_code == 404
