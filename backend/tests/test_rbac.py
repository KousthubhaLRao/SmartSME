"""Role permissions, the invite flow and sign-in throttling.

Every role is exercised against the endpoints that matter for it, from both
sides: what it may do, and what it must be refused. The refusals are the point —
a permission test that only checks the happy path proves nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.core.roles import ADMIN, EMPLOYEE, OWNER, SUPERUSER


# ---------------------------------------------------------------------------
# The permission table itself
# ---------------------------------------------------------------------------
def test_role_permissions_are_what_we_think_they_are():
    from app.core.roles import P, permissions_for

    # An admin tunes a business but never touches its data.
    admin = permissions_for(ADMIN)
    assert P.CONFIG_WRITE in admin
    assert P.DATA_READ in admin
    assert P.TXN_WRITE not in admin
    assert P.DATA_MANAGE not in admin
    assert P.CATALOG_WRITE not in admin

    # An employee records activity but cannot undo it or reconfigure anything.
    employee = permissions_for(EMPLOYEE)
    assert employee == frozenset({P.DATA_READ, P.TXN_WRITE})

    # Only platform roles cross tenant boundaries.
    assert P.CROSS_TENANT in permissions_for(SUPERUSER)
    assert P.CROSS_TENANT in admin
    assert P.CROSS_TENANT not in permissions_for(OWNER)

    # An unrecognised role is powerless rather than unrestricted.
    assert permissions_for("typo") == frozenset()


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------
def test_employee_can_record_business_activity(employee_client, workspace):
    sale = employee_client.post(
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
    sale_id = sale.json()["id"]

    assert (
        employee_client.post("/api/expenses", json={"description": "Tea", "amount": 40}).status_code
        == 201
    )
    assert (
        employee_client.post(f"/api/sales/{sale_id}/payment", json={"amount": 10}).status_code
        == 200
    )
    # Reads are fine too.
    for path in ("/api/dashboard", "/api/products", "/api/parties", "/api/reports/overview"):
        assert employee_client.get(path).status_code == 200, path


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("put", "/api/settings", {"name": "Renamed", "taxRate": 5}),
        ("post", "/api/workflow/rules", {"name": "r", "eventType": "SALE_CREATED"}),
        ("post", "/api/products", {"name": "New product"}),
        ("post", "/api/parties", {"type": "customer", "name": "New party"}),
        ("post", "/api/parties/settle-all/receivable", None),
        ("post", "/api/events/drain", None),
    ],
)
def test_employee_is_refused_everything_else(employee_client, method, path, body):
    call = getattr(employee_client, method)
    response = call(path, json=body) if body is not None else call(path)
    assert response.status_code == 403, f"{method.upper()} {path} -> {response.status_code}"


def test_employee_cannot_delete_or_cancel(employee_client, client, workspace):
    # The owner creates something, the employee must not be able to undo it.
    sale_id = client.post(
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
    ).json()["id"]

    assert employee_client.post(f"/api/sales/{sale_id}/cancel").status_code == 403
    assert (
        employee_client.patch(f"/api/sales/{sale_id}/date", json={"date": "2026-01-01"}).status_code
        == 403
    )
    assert employee_client.delete(f"/api/products/{workspace['productId']}").status_code == 403


def test_employee_cannot_manage_the_team(employee_client):
    assert employee_client.get("/api/users").status_code == 403
    assert (
        employee_client.post(
            "/api/users/invites", json={"email": "x@smoketest.dev", "role": "employee"}
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# Admin: configuration yes, data no
# ---------------------------------------------------------------------------
def test_admin_needs_a_business_id(admin_client):
    r = admin_client.get("/api/dashboard")
    assert r.status_code == 400
    assert "businessId" in r.json()["detail"]


def test_admin_can_read_and_reconfigure_any_business(admin_client, business_id):
    q = {"businessId": business_id}
    assert admin_client.get("/api/dashboard", params=q).status_code == 200
    before = admin_client.get("/api/settings", params=q)
    assert before.status_code == 200
    original = before.json()["business"]

    updated = admin_client.put(
        "/api/settings", params=q, json={"name": "Tuned By Admin", "taxRate": 9}
    )
    assert updated.status_code == 200
    assert admin_client.get("/api/settings", params=q).json()["business"]["taxRate"] == 9

    # Put it back: other tests assert on this business's name and tax rate.
    admin_client.put(
        "/api/settings",
        params=q,
        json={"name": original["name"], "taxRate": original["taxRate"]},
    )

    rule = admin_client.post(
        "/api/workflow/rules",
        params=q,
        json={"name": "Admin rule", "eventType": "SALE_CREATED", "actionType": "notify"},
    )
    assert rule.status_code == 201
    admin_client.delete(f"/api/workflow/rules/{rule.json()['id']}", params=q)


def test_admin_cannot_touch_business_data(admin_client, business_id, workspace):
    q = {"businessId": business_id}
    sale = admin_client.post(
        "/api/sales",
        params=q,
        json={
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 1,
                    "unitPrice": 140,
                }
            ]
        },
    )
    assert sale.status_code == 403
    assert admin_client.post("/api/products", params=q, json={"name": "Nope"}).status_code == 403
    assert (
        admin_client.post(
            "/api/expenses", params=q, json={"description": "n", "amount": 1}
        ).status_code
        == 403
    )
    assert admin_client.post("/api/parties/settle-all/receivable", params=q).status_code == 403
    assert (
        admin_client.delete(f"/api/products/{workspace['productId']}", params=q).status_code == 403
    )
    # Nor may it decide who works there.
    assert admin_client.get("/api/users", params=q).status_code == 403


# ---------------------------------------------------------------------------
# Superuser
# ---------------------------------------------------------------------------
def test_superuser_can_do_anything_to_any_business(superuser_client, business_id, workspace):
    q = {"businessId": business_id}
    sale = superuser_client.post(
        "/api/sales",
        params=q,
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
    assert (
        superuser_client.post(f"/api/sales/{sale.json()['id']}/cancel", params=q).status_code == 200
    )
    assert superuser_client.get("/api/users", params=q).status_code == 200


def test_platform_roles_can_list_businesses(superuser_client, admin_client, business_id):
    for c in (superuser_client, admin_client):
        r = c.get("/api/businesses")
        assert r.status_code == 200
        assert any(b["id"] == business_id for b in r.json()["rows"])


def test_tenant_roles_cannot_list_businesses(client, employee_client):
    assert client.get("/api/businesses").status_code == 403
    assert employee_client.get("/api/businesses").status_code == 403


def test_owner_cannot_reach_another_business(client, other_business_id):
    """The businessId parameter is ignored for tenant roles, and asking for
    someone else's is a 404 rather than a 403 — no probing for tenants."""
    r = client.get("/api/dashboard", params={"businessId": other_business_id})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------
def test_invite_round_trip(client, fresh_client):
    email = f"invited-{uuid.uuid4().hex[:10]}@smoketest.dev"
    created = client.post("/api/users/invites", json={"email": email, "role": "employee"})
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    assert created.json()["joinUrl"].endswith(f"/join/{token}")

    preview = fresh_client.get(f"/api/auth/invite/{token}")
    assert preview.status_code == 200
    assert preview.json()["email"] == email
    assert preview.json()["role"] == "employee"

    accepted = fresh_client.post(
        "/api/auth/accept-invite",
        json={"token": token, "name": "Invited Person", "password": "invited1234"},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["user"]["role"] == EMPLOYEE
    # Signed in, and in the inviting business.
    assert fresh_client.get("/api/auth/me").json()["user"]["email"] == email

    # A token is single use.
    again = fresh_client.post(
        "/api/auth/accept-invite",
        json={"token": token, "name": "Someone Else", "password": "invited1234"},
    )
    assert again.status_code in (404, 409)


def test_invite_rejects_bad_tokens_and_roles(client, fresh_client):
    assert fresh_client.get("/api/auth/invite/not-a-real-token").status_code == 404
    assert (
        fresh_client.post(
            "/api/auth/accept-invite",
            json={"token": "nonsense", "name": "X", "password": "password123"},
        ).status_code
        == 404
    )
    bad_role = client.post(
        "/api/users/invites", json={"email": "x@smoketest.dev", "role": "superuser"}
    )
    assert bad_role.status_code == 400


def test_revoked_invite_cannot_be_accepted(client, fresh_client):
    email = f"revoked-{uuid.uuid4().hex[:10]}@smoketest.dev"
    created = client.post("/api/users/invites", json={"email": email, "role": "employee"})
    token = created.json()["token"]
    assert client.delete(f"/api/users/invites/{created.json()['id']}").status_code == 200
    assert fresh_client.get(f"/api/auth/invite/{token}").status_code == 404


def test_team_listing_and_last_owner_guard(client):
    listing = client.get("/api/users")
    assert listing.status_code == 200
    body = listing.json()
    assert body["members"]
    me = next(m for m in body["members"] if m["role"] == OWNER)

    # The only owner cannot demote or remove themselves.
    assert (
        client.put(
            f"/api/users/{me['id']}/role", json={"email": me["email"], "role": "employee"}
        ).status_code
        == 400
    )
    assert client.delete(f"/api/users/{me['id']}").status_code == 400


# ---------------------------------------------------------------------------
# Sign-in throttling
# ---------------------------------------------------------------------------
def _fail_sign_in(client, email: str, times: int) -> list[int]:
    return [
        client.post(
            "/api/auth/sign-in", json={"email": email, "password": "wrong-password"}
        ).status_code
        for _ in range(times)
    ]


def test_owner_is_locked_out_after_repeated_failures(fresh_client, throttled_owner):
    email = throttled_owner["email"]
    codes = _fail_sign_in(fresh_client, email, 5)
    assert codes == [401, 401, 401, 401, 401]

    # The sixth attempt is refused before the password is even checked.
    locked = fresh_client.post("/api/auth/sign-in", json={"email": email, "password": "wrong"})
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers

    # And the correct password does not help while the lock stands.
    with_right_password = fresh_client.post(
        "/api/auth/sign-in", json={"email": email, "password": throttled_owner["password"]}
    )
    assert with_right_password.status_code == 429


def test_unknown_emails_are_locked_the_same_way(fresh_client):
    """Otherwise the lockout response would reveal which addresses exist."""
    email = f"ghost-{uuid.uuid4().hex[:10]}@smoketest.dev"
    _fail_sign_in(fresh_client, email, 5)
    assert (
        fresh_client.post("/api/auth/sign-in", json={"email": email, "password": "x"}).status_code
        == 429
    )


def test_employees_are_exempt_from_the_account_lock(fresh_client, throttled_employee):
    email = throttled_employee["email"]
    codes = _fail_sign_in(fresh_client, email, 7)
    assert set(codes) == {401}, "an employee account should never lock"

    ok = fresh_client.post(
        "/api/auth/sign-in", json={"email": email, "password": throttled_employee["password"]}
    )
    assert ok.status_code == 200


def test_a_successful_sign_in_clears_the_streak(fresh_client, throttled_owner):
    email, password = throttled_owner["email"], throttled_owner["password"]
    _fail_sign_in(fresh_client, email, 4)
    assert (
        fresh_client.post(
            "/api/auth/sign-in", json={"email": email, "password": password}
        ).status_code
        == 200
    )
    # Four more failures must not add up to a lock across that success.
    assert _fail_sign_in(fresh_client, email, 4) == [401, 401, 401, 401]


def test_lock_duration_doubles(monkeypatch):
    """The arithmetic on its own, without waiting fifteen minutes for it."""
    from app.core import throttle

    now = datetime(2026, 9, 13, 12, 0, 0)
    assert throttle._lock_expiry(4, now) is None
    assert throttle._lock_expiry(5, now) == now + timedelta(minutes=15)
    assert throttle._lock_expiry(10, now) == now + timedelta(minutes=30)
    assert throttle._lock_expiry(15, now) == now + timedelta(minutes=60)
    # Capped, so a forgotten account cannot be locked for a month.
    assert throttle._lock_expiry(500, now) == now + throttle.MAX_LOCK
