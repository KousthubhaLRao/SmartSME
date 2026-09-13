"""Paging on the list endpoints.

The regression these guard against is subtle: it is easy to paginate the rows
and forget that the totals beside them were being summed from those same rows,
at which point a dashboard quietly starts reporting one page's worth of money.
Every test here checks the envelope *and* that the statistics still describe the
whole set.
"""

from __future__ import annotations

import uuid

import pytest

PAGED_ENDPOINTS = [
    "/api/sales",
    "/api/purchases",
    "/api/products",
    "/api/parties",
    "/api/expenses",
    "/api/events",
    "/api/notifications",
]


@pytest.fixture(scope="module")
def expenses(client):
    """Six expenses of a known size, in their own category."""
    category = f"Paging{uuid.uuid4().hex[:6]}"
    for i in range(6):
        r = client.post(
            "/api/expenses",
            json={"category": category, "description": f"Paged expense {i}", "amount": 100},
        )
        assert r.status_code == 201, r.text
    return {"category": category, "count": 6, "each": 100}


@pytest.mark.parametrize("path", PAGED_ENDPOINTS)
def test_every_list_endpoint_reports_its_paging(client, path):
    body = client.get(path).json()
    assert "page" in body, f"{path} has no page envelope"
    page = body["page"]
    assert {"page", "pageSize", "total", "pages", "hasMore"} == page.keys()
    assert page["page"] == 1
    assert page["pageSize"] == 50
    assert page["total"] >= len(body["rows"])


@pytest.mark.parametrize("path", PAGED_ENDPOINTS)
def test_page_size_is_honoured(client, path):
    body = client.get(path, params={"pageSize": 2}).json()
    assert len(body["rows"]) <= 2
    assert body["page"]["pageSize"] == 2
    if body["page"]["total"] > 2:
        assert body["page"]["hasMore"] is True
        assert body["page"]["pages"] >= 2


def test_pages_do_not_overlap(client, expenses):
    first = client.get("/api/expenses", params={"pageSize": 3, "page": 1}).json()
    second = client.get("/api/expenses", params={"pageSize": 3, "page": 2}).json()

    assert len(first["rows"]) == 3
    assert len(second["rows"]) == 3
    assert {r["id"] for r in first["rows"]}.isdisjoint({r["id"] for r in second["rows"]})
    assert second["page"]["page"] == 2


def test_a_page_past_the_end_is_empty_rather_than_an_error(client):
    body = client.get("/api/expenses", params={"page": 9999}).json()
    assert body["rows"] == []
    assert body["page"]["hasMore"] is False


def test_totals_describe_everything_not_just_the_page(client, expenses):
    """The whole point: shrinking the page must not shrink the money."""
    everything = client.get("/api/expenses", params={"pageSize": 200}).json()
    one_row = client.get("/api/expenses", params={"pageSize": 1}).json()

    assert len(one_row["rows"]) == 1
    assert one_row["stats"] == everything["stats"]
    assert one_row["stats"]["count"] == one_row["page"]["total"]
    # The category breakdown is aggregated in SQL, so it is unaffected too.
    assert one_row["byCategory"] == everything["byCategory"]
    mine = next(c for c in one_row["byCategory"] if c["label"] == expenses["category"])
    assert mine["value"] == expenses["count"] * expenses["each"]


def test_sale_totals_survive_a_small_page(client, workspace):
    everything = client.get("/api/sales", params={"pageSize": 200}).json()
    one_row = client.get("/api/sales", params={"pageSize": 1}).json()
    assert one_row["stats"] == everything["stats"]
    assert one_row["stats"]["count"] > 1, "the fixture business has several sales"


def test_purchase_totals_survive_a_small_page(client, workspace):
    everything = client.get("/api/purchases", params={"pageSize": 200}).json()
    one_row = client.get("/api/purchases", params={"pageSize": 1}).json()
    assert one_row["stats"] == everything["stats"]


def test_product_stats_survive_a_small_page(client, workspace):
    everything = client.get("/api/products", params={"pageSize": 200}).json()
    one_row = client.get("/api/products", params={"pageSize": 1}).json()
    assert one_row["stats"] == everything["stats"]
    # Movements name products beyond the current page, and must still resolve.
    assert all(m["product"] for m in one_row["movements"] if m.get("product") is not None)


def test_party_balances_survive_a_small_page(client, workspace):
    everything = client.get("/api/parties", params={"pageSize": 200}).json()
    one_row = client.get("/api/parties", params={"pageSize": 1}).json()
    assert one_row["stats"] == everything["stats"]


def test_outstanding_is_attached_to_the_right_party(client, workspace):
    """Outstanding documents are now fetched only for the page's parties, so the
    join has to keep pointing at the party that actually owes the money."""
    sale = client.post(
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
    assert sale.status_code == 201, sale.text
    invoice = sale.json()["invoiceNumber"]

    found = None
    page = 1
    while found is None:
        body = client.get("/api/parties", params={"pageSize": 2, "page": page}).json()
        for row in body["rows"]:
            if row["id"] == workspace["customerId"]:
                found = row
        if not body["page"]["hasMore"]:
            break
        page += 1

    assert found is not None, "the customer should appear on some page"
    assert any(o["ref"] == invoice for o in found["outstanding"])
    # And nothing that is already settled leaks in.
    assert all(o["due"] > 0 for o in found["outstanding"])

    client.post(f"/api/parties/{workspace['customerId']}/settle")


@pytest.mark.parametrize("params", [{"pageSize": 0}, {"pageSize": 500}, {"page": 0}])
def test_nonsense_paging_is_rejected(client, params):
    assert client.get("/api/expenses", params=params).status_code == 422
