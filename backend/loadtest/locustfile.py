"""Load profile for SmartSME.

Models a shop floor rather than a synthetic benchmark: most of the traffic is
people *looking* at things — the dashboard on a wall screen, the sales list, a
product lookup mid-conversation — with a steady trickle of writes underneath.
The weights below are roughly 8 reads per write, which is what an SME's day
actually looks like.

Run it against a seeded database (`python -m loadtest.seed`), never against real
data: every user signs in as the shared load-test owner and records sales.

    locust -f loadtest/locustfile.py --host http://localhost:8000
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
        --headless -u 200 -r 20 -t 60s

Each simulated user signs in once and keeps its session cookie, so the numbers
measure the app rather than PBKDF2: password hashing is deliberately slow, and
re-authenticating every request would swamp everything else.
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, events, task

EMAIL = os.environ.get("LOADTEST_EMAIL", "loadtest@smoketest.dev")
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "loadtest1234")

#: Filled in by the first user to sign in, then shared — every simulated user is
#: the same shop, which is the point.
CATALOG: dict[str, list[str]] = {"products": [], "customers": []}


@events.test_start.add_listener
def _announce(environment, **_kwargs):
    print(f"[loadtest] signing in as {EMAIL} against {environment.host}")


class Shopkeeper(HttpUser):
    """One person with the app open."""

    wait_time = between(0.5, 2.5)

    def on_start(self) -> None:
        response = self.client.post(
            "/api/auth/sign-in",
            json={"email": EMAIL, "password": PASSWORD},
            name="/api/auth/sign-in",
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"could not sign in as {EMAIL}: {response.status_code} {response.text[:200]}. "
                "Seed the database first: python -m loadtest.seed"
            )
        if not CATALOG["products"]:
            self._load_catalog()

    def _load_catalog(self) -> None:
        products = self.client.get("/api/products?pageSize=50", name="/api/products [setup]")
        if products.status_code == 200:
            CATALOG["products"] = [p["id"] for p in products.json()["rows"]]
        parties = self.client.get("/api/parties?pageSize=50", name="/api/parties [setup]")
        if parties.status_code == 200:
            CATALOG["customers"] = [
                p["id"] for p in parties.json()["rows"] if p.get("type") == "customer"
            ]

    # -- Reads: the bulk of a working day ---------------------------------
    @task(20)
    def dashboard(self) -> None:
        self.client.get("/api/dashboard", name="/api/dashboard")

    @task(12)
    def sales_list(self) -> None:
        page = random.randint(1, 3)
        self.client.get(f"/api/sales?page={page}", name="/api/sales")

    @task(8)
    def purchases_list(self) -> None:
        self.client.get("/api/purchases", name="/api/purchases")

    @task(8)
    def products_list(self) -> None:
        self.client.get("/api/products", name="/api/products")

    @task(6)
    def parties_list(self) -> None:
        self.client.get("/api/parties", name="/api/parties")

    @task(5)
    def expenses_list(self) -> None:
        self.client.get("/api/expenses", name="/api/expenses")

    @task(4)
    def reports(self) -> None:
        self.client.get("/api/reports/revenue?days=30", name="/api/reports/revenue")

    @task(3)
    def notifications(self) -> None:
        self.client.get("/api/notifications/unread-count", name="/api/notifications/unread-count")

    @task(2)
    def events(self) -> None:
        self.client.get("/api/events", name="/api/events")

    @task(2)
    def one_sale(self) -> None:
        """Opening an invoice, which is a different query shape to the list."""
        listing = self.client.get("/api/sales?pageSize=5", name="/api/sales [detail lookup]")
        if listing.status_code != 200:
            return
        rows = listing.json().get("rows") or []
        if rows:
            self.client.get(f"/api/sales/{random.choice(rows)['id']}", name="/api/sales/:id")

    # -- Writes: the trickle underneath ------------------------------------
    @task(3)
    def record_sale(self) -> None:
        if not CATALOG["products"]:
            return
        self.client.post(
            "/api/sales",
            name="/api/sales [create]",
            json={
                "partyId": random.choice(CATALOG["customers"]) if CATALOG["customers"] else None,
                "items": [
                    {
                        "productId": random.choice(CATALOG["products"]),
                        "description": "Load test line",
                        "quantity": random.randint(1, 4),
                        "unitPrice": 140,
                    }
                ],
                "amountPaid": 0,
            },
        )

    @task(2)
    def record_expense(self) -> None:
        self.client.post(
            "/api/expenses",
            name="/api/expenses [create]",
            json={
                "category": random.choice(["Rent", "Utilities", "Transport", "Supplies"]),
                "description": "Load test expense",
                "amount": random.randint(50, 5000),
            },
        )

    @task(1)
    def smart_input(self) -> None:
        """The parser, which is CPU work rather than database work."""
        self.client.post(
            "/api/input/parse-text",
            name="/api/input/parse-text",
            json={
                "text": random.choice(
                    [
                        "sold 3 kg rice to Anita Stores",
                        "Anita ko 5 kilo chawal becha",
                        "ಅನಿತಾಗೆ ೪ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ",
                        "paid 2000 for electricity",
                    ]
                )
            },
        )
