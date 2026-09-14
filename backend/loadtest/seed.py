"""Build a database worth load testing against.

An empty table is fast at any concurrency, so measuring against one measures
nothing. This creates a business with a realistic amount of history — thousands
of sales across a year, a full catalogue, a party list — so the queries have
something to sort and page through.

    python -m loadtest.seed              # ~4000 sales
    python -m loadtest.seed --sales 20000

Safe to re-run: it reuses the same load-test business rather than piling up new
ones, and it never touches another tenant's rows.
"""

from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Business, Party, Product, Sale, SaleItem, User
from app.workflow import default_rules

BUSINESS_NAME = "Load Test Traders"
EMAIL = "loadtest@smoketest.dev"
PASSWORD = "loadtest1234"

PRODUCTS = [
    ("Rice 25kg", "bag", 1100, 1350),
    ("Sugar 1kg", "kg", 42, 55),
    ("Cooking Oil 1L", "litre", 110, 145),
    ("Wheat Flour 10kg", "bag", 380, 460),
    ("Tea Powder 500g", "packet", 210, 265),
    ("Toor Dal 1kg", "kg", 130, 165),
    ("Salt 1kg", "kg", 18, 26),
    ("Biscuits", "packet", 20, 30),
    ("Detergent 1kg", "packet", 95, 125),
    ("Milk Powder 500g", "packet", 240, 310),
]

CUSTOMERS = [
    "Anita Stores",
    "Kumar Traders",
    "Sunrise Wholesale",
    "Lakshmi Provisions",
    "New Bharat Kirana",
    "Raj General Store",
    "Sri Venkateshwara Stores",
    "Modern Mart",
    "Green Valley Foods",
    "City Supermarket",
]
SUPPLIERS = ["ABC Suppliers", "Metro Distributors", "Krishna Agencies", "Prime Wholesale"]


def seed(sales_count: int) -> None:
    with SessionLocal() as db:
        business = db.scalar(select(Business).where(Business.name == BUSINESS_NAME))
        if business is None:
            business = Business(name=BUSINESS_NAME, currency="INR", tax_rate=18)
            db.add(business)
            db.flush()
            db.add_all(default_rules(business.id))
            print(f"created business {business.id}")
        else:
            print(f"reusing business {business.id}")

        if db.scalar(select(User.id).where(User.email == EMAIL)) is None:
            db.add(
                User(
                    business_id=business.id,
                    email=EMAIL,
                    name="Load Test Owner",
                    password_hash=hash_password(PASSWORD),
                    role="owner",
                )
            )
            print(f"created user {EMAIL} / {PASSWORD}")

        products = list(db.scalars(select(Product).where(Product.business_id == business.id)))
        if not products:
            for name, unit, cost, price in PRODUCTS:
                db.add(
                    Product(
                        business_id=business.id,
                        name=name,
                        unit=unit,
                        purchase_price=cost,
                        selling_price=price,
                        # Deliberately huge: a load test must not run the shop
                        # out of stock halfway through and turn writes into 400s.
                        stock=10_000_000,
                        low_stock_threshold=10,
                    )
                )
            db.flush()
            products = list(db.scalars(select(Product).where(Product.business_id == business.id)))
            print(f"created {len(products)} products")

        parties = list(db.scalars(select(Party).where(Party.business_id == business.id)))
        if not parties:
            for name in CUSTOMERS:
                db.add(Party(business_id=business.id, type="customer", name=name))
            for name in SUPPLIERS:
                db.add(Party(business_id=business.id, type="supplier", name=name))
            db.flush()
            parties = list(db.scalars(select(Party).where(Party.business_id == business.id)))
            print(f"created {len(parties)} parties")

        db.commit()
        business_id = business.id
        product_rows = [(p.id, p.selling_price) for p in products]
        customer_ids = [p.id for p in parties if p.type == "customer"]

    existing = _count_sales(business_id)
    if existing >= sales_count:
        print(f"{existing} sales already present; nothing to do")
        return

    to_create = sales_count - existing
    print(f"creating {to_create} sales (this writes directly, bypassing the event bus)")
    _bulk_sales(business_id, product_rows, customer_ids, to_create, start_at=existing)
    print(f"done: {_count_sales(business_id)} sales")


def _count_sales(business_id: uuid.UUID) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(Sale.id)).where(Sale.business_id == business_id)) or 0


def _bulk_sales(
    business_id: uuid.UUID,
    products: list[tuple[uuid.UUID, float]],
    customers: list[uuid.UUID],
    count: int,
    start_at: int,
) -> None:
    """Insert history in batches.

    The domain layer is bypassed on purpose: this is scenery, not behaviour
    under test, and going through it would publish a few thousand events and
    take minutes rather than seconds.
    """
    now = datetime.now()
    batch = 500
    made = 0
    while made < count:
        rows: list[Sale] = []
        items: list[SaleItem] = []
        with SessionLocal() as db:
            for i in range(min(batch, count - made)):
                number = start_at + made + i + 1
                product_id, price = random.choice(products)
                quantity = random.randint(1, 6)
                subtotal = round(price * quantity, 2)
                tax = round(subtotal * 0.18, 2)
                # The primary key default is applied at INSERT, so it has to be
                # generated here for the line item to point at it.
                sale_id = uuid.uuid4()
                sale = Sale(
                    id=sale_id,
                    business_id=business_id,
                    party_id=random.choice(customers) if customers else None,
                    invoice_number=f"LT-{number:07d}",
                    status="completed",
                    subtotal=subtotal,
                    tax=tax,
                    total=round(subtotal + tax, 2),
                    amount_paid=round(subtotal + tax, 2),
                    payment_status="paid",
                    source="form",
                    # Spread across a year so the date-ordered index has work.
                    date=now - timedelta(minutes=random.randint(0, 525_600)),
                )
                rows.append(sale)
                items.append(
                    SaleItem(
                        sale_id=sale_id,
                        product_id=product_id,
                        description="Seeded line",
                        quantity=quantity,
                        unit_price=price,
                        line_total=subtotal,
                    )
                )
            db.add_all(rows)
            db.add_all(items)
            db.commit()
        made += len(rows)
        print(f"  {made}/{count}", end="\r", flush=True)
    print()


def reset() -> None:
    """Remove everything this script created."""
    with SessionLocal() as db:
        business = db.scalar(select(Business).where(Business.name == BUSINESS_NAME))
        if business is None:
            print("nothing to remove")
            return
        db.execute(delete(Business).where(Business.id == business.id))
        db.commit()
    print("load-test business removed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loadtest.seed", description=__doc__)
    parser.add_argument("--sales", type=int, default=4000, help="Total sales to end up with.")
    parser.add_argument("--reset", action="store_true", help="Delete the load-test business.")
    args = parser.parse_args(argv)

    if args.reset:
        reset()
        return 0
    seed(args.sales)
    return 0


if __name__ == "__main__":
    sys.exit(main())
