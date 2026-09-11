"""Demo tenant, seeded on first boot so the app is usable immediately."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.security import hash_password
from .core.utils import round2
from .models import (
    Business,
    Event,
    Expense,
    Notification,
    Party,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    StockMovement,
    User,
)
from .workflow import default_rules

DEMO_EMAIL = "demo@smartsme.app"
DEMO_PASSWORD = "demo1234"


def seed_if_empty(db: Session) -> bool:
    """Seed a realistic demo tenant. Returns True if it actually seeded."""
    if db.scalar(select(Business.id).limit(1)):
        return False

    biz = Business(
        name="Kirana Fresh Traders",
        gst_number="29ABCDE1234F1Z5",
        pan_number="ABCDE1234F",
        address="12 Market Road, Bengaluru, Karnataka 560001",
        phone="+91 98450 12345",
        email="hello@kiranafresh.example",
        currency="INR",
        tax_rate=18,
        invoice_prefix="INV",
    )
    db.add(biz)
    db.flush()

    db.add(
        User(
            business_id=biz.id,
            email=DEMO_EMAIL,
            name="Demo Owner",
            password_hash=hash_password(DEMO_PASSWORD),
            role="owner",
        )
    )

    # ---- Parties ----
    kumar = Party(
        business_id=biz.id,
        type="customer",
        name="Kumar Traders",
        phone="+919000011111",
        gst_number="29AAAAA0000A1Z1",
    )
    anita = Party(business_id=biz.id, type="customer", name="Anita Stores", phone="+919000022222")
    abc = Party(
        business_id=biz.id,
        type="supplier",
        name="ABC Suppliers",
        phone="+919000033333",
        gst_number="29BBBBB0000B1Z2",
    )
    sunrise = Party(
        business_id=biz.id, type="supplier", name="Sunrise Wholesale", phone="+919000044444"
    )
    db.add_all([kumar, anita, abc, sunrise])

    # ---- Products ----
    rice = Product(
        business_id=biz.id,
        name="Rice Bag 25kg",
        sku="RICE-25",
        hsn="1006",
        unit="bag",
        purchase_price=1100,
        selling_price=1350,
        stock=40,
        low_stock_threshold=15,
    )
    sugar = Product(
        business_id=biz.id,
        name="Sugar Packet 1kg",
        sku="SUG-1",
        hsn="1701",
        unit="pkt",
        purchase_price=42,
        selling_price=52,
        stock=8,
        low_stock_threshold=20,
    )
    oil = Product(
        business_id=biz.id,
        name="Cooking Oil 1L",
        sku="OIL-1",
        hsn="1512",
        unit="ltr",
        purchase_price=130,
        selling_price=160,
        stock=60,
        low_stock_threshold=25,
    )
    flour = Product(
        business_id=biz.id,
        name="Wheat Flour 10kg",
        sku="FLR-10",
        hsn="1101",
        unit="bag",
        purchase_price=340,
        selling_price=410,
        stock=22,
        low_stock_threshold=10,
    )
    tea = Product(
        business_id=biz.id,
        name="Tea Powder 500g",
        sku="TEA-500",
        hsn="0902",
        unit="pkt",
        purchase_price=210,
        selling_price=265,
        stock=5,
        low_stock_threshold=12,
    )
    db.add_all([rice, sugar, oil, flour, tea])
    db.flush()

    now = datetime.now()

    # ---- A paid sale (pre-processed so the dashboard has data) ----
    sale1_sub = 10 * 1350 + 5 * 160
    sale1_tax = round2(sale1_sub * 0.18)
    sale1_total = round2(sale1_sub + sale1_tax)
    sale1_when = now - timedelta(days=2)
    sale1 = Sale(
        business_id=biz.id,
        party_id=kumar.id,
        invoice_number="INV-0001",
        subtotal=sale1_sub,
        tax=sale1_tax,
        total=sale1_total,
        amount_paid=sale1_total,
        payment_status="paid",
        source="form",
        date=sale1_when,
        created_at=sale1_when,
    )
    db.add(sale1)
    db.flush()
    db.add_all(
        [
            SaleItem(
                sale_id=sale1.id,
                product_id=rice.id,
                description="Rice Bag 25kg",
                quantity=10,
                unit_price=1350,
                line_total=13500,
            ),
            SaleItem(
                sale_id=sale1.id,
                product_id=oil.id,
                description="Cooking Oil 1L",
                quantity=5,
                unit_price=160,
                line_total=800,
            ),
        ]
    )

    # ---- An unpaid sale (receivable) ----
    sale2_sub = 3 * 410
    sale2_tax = round2(sale2_sub * 0.18)
    sale2_total = round2(sale2_sub + sale2_tax)
    sale2_when = now - timedelta(days=1)
    sale2 = Sale(
        business_id=biz.id,
        party_id=anita.id,
        invoice_number="INV-0002",
        subtotal=sale2_sub,
        tax=sale2_tax,
        total=sale2_total,
        amount_paid=0,
        payment_status="unpaid",
        source="nlp",
        date=sale2_when,
        created_at=sale2_when,
    )
    db.add(sale2)
    db.flush()
    db.add(
        SaleItem(
            sale_id=sale2.id,
            product_id=flour.id,
            description="Wheat Flour 10kg",
            quantity=3,
            unit_price=410,
            line_total=1230,
        )
    )
    anita.balance = sale2_total

    # ---- A part-paid purchase (payable) ----
    pur_sub = 20 * 1100
    pur_tax = round2(pur_sub * 0.18)
    pur_total = round2(pur_sub + pur_tax)
    pur_when = now - timedelta(days=3)
    pur1 = Purchase(
        business_id=biz.id,
        party_id=abc.id,
        reference_number="PO-0001",
        subtotal=pur_sub,
        tax=pur_tax,
        total=pur_total,
        amount_paid=round2(pur_total / 2),
        payment_status="partial",
        source="form",
        date=pur_when,
        created_at=pur_when,
    )
    db.add(pur1)
    db.flush()
    db.add(
        PurchaseItem(
            purchase_id=pur1.id,
            product_id=rice.id,
            description="Rice Bag 25kg",
            quantity=20,
            unit_price=1100,
            line_total=22000,
        )
    )
    abc.balance = round2(pur_total - pur_total / 2)

    # ---- Expenses ----
    db.add_all(
        [
            Expense(
                business_id=biz.id,
                category="Rent",
                description="Shop rent - monthly",
                amount=18000,
                date=now - timedelta(days=5),
            ),
            Expense(
                business_id=biz.id,
                category="Utilities",
                description="Electricity bill",
                amount=3200,
                date=now - timedelta(days=4),
            ),
            Expense(
                business_id=biz.id,
                category="Transport",
                description="Delivery van fuel",
                amount=2100,
                date=now - timedelta(days=1),
            ),
        ]
    )

    # ---- Stock movement history for the seeded transactions ----
    db.add_all(
        [
            StockMovement(
                business_id=biz.id,
                product_id=rice.id,
                delta=20,
                reason="purchase",
                ref_type="purchase",
                ref_id=pur1.id,
                note="PO-0001",
            ),
            StockMovement(
                business_id=biz.id,
                product_id=rice.id,
                delta=-10,
                reason="sale",
                ref_type="sale",
                ref_id=sale1.id,
                note="INV-0001",
            ),
            StockMovement(
                business_id=biz.id,
                product_id=oil.id,
                delta=-5,
                reason="sale",
                ref_type="sale",
                ref_id=sale1.id,
                note="INV-0001",
            ),
            StockMovement(
                business_id=biz.id,
                product_id=flour.id,
                delta=-3,
                reason="sale",
                ref_type="sale",
                ref_id=sale2.id,
                note="INV-0002",
            ),
        ]
    )

    # ---- Already-processed events, so the monitor has history ----
    db.add_all(
        [
            Event(
                business_id=biz.id,
                type="SALE_CREATED",
                payload={"saleId": str(sale1.id)},
                status="done",
                processed_at=sale1_when,
            ),
            Event(
                business_id=biz.id,
                type="SALE_CREATED",
                payload={"saleId": str(sale2.id)},
                status="done",
                processed_at=sale2_when,
            ),
            Event(
                business_id=biz.id,
                type="PURCHASE_CREATED",
                payload={"purchaseId": str(pur1.id)},
                status="done",
                processed_at=pur_when,
            ),
            Event(
                business_id=biz.id,
                type="STOCK_UPDATED",
                payload={"productId": str(tea.id)},
                status="done",
                processed_at=sale2_when,
            ),
        ]
    )

    # ---- Default workflow rules ----
    db.add_all(default_rules(biz.id))

    # ---- Notifications matching the low-stock products ----
    db.add_all(
        [
            Notification(
                business_id=biz.id,
                type="low_stock",
                severity="warning",
                title="Low stock: Sugar Packet 1kg",
                message="Only 8 pkt left (threshold 20). Consider restocking.",
            ),
            Notification(
                business_id=biz.id,
                type="low_stock",
                severity="warning",
                title="Low stock: Tea Powder 500g",
                message="Only 5 pkt left (threshold 12). Consider restocking.",
            ),
            Notification(
                business_id=biz.id,
                type="payment_pending",
                severity="info",
                title="Receivable pending",
                message=f"Anita Stores owes ₹{sale2_total:,.2f} on INV-0002.",
            ),
        ]
    )

    db.commit()
    return True
