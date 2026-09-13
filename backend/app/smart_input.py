"""Smart Input: turn a note or an image into a confirmable draft.

The LLM (or the regex fallback) extracts raw fields; this module *grounds* them
against the tenant's own data: fuzzy-matching the party and products, letting a
known party correct the sale-vs-purchase direction, and expanding "the entire
inventory" into one line per in-stock product. Nothing is written here - the
user confirms first, then `publish_draft` runs it through the domain layer.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai.client import ai_status
from .ai.nlp import parse_command
from .ai.ocr import ALLOWED_MEDIA, parse_invoice_image
from .core.utils import parse_date_input, round2
from .domain import purchases as purchases_domain
from .domain import sales as sales_domain
from .domain.catalog import create_expense
from .models import Party, Product
from .schemas import ExpenseInput, LineInput, PurchaseInput, SaleInput

T = TypeVar("T", Party, Product)


def _norm(s: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace, so "Anita Stores." and
    "ANITA  STORES" compare equal."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())).strip()


def best_match(items: list[T], query: str | None) -> T | None:
    """Exact (normalised), then substring either way, then token-subset, so
    "Anita" resolves "Anita Stores"."""
    if not query:
        return None
    needle = _norm(query)
    if not needle:
        return None

    for item in items:
        if _norm(item.name) == needle:
            return item

    for item in items:
        n = _norm(item.name)
        if len(n) > 1 and (n in needle or needle in n):
            return item

    needle_tokens = [t for t in needle.split(" ") if t]
    for item in items:
        item_tokens = [t for t in _norm(item.name).split(" ") if t]
        if not item_tokens:
            continue
        short, long_set = (
            (needle_tokens, set(item_tokens))
            if len(needle_tokens) <= len(item_tokens)
            else (item_tokens, set(needle_tokens))
        )
        if short and all(t in long_set for t in short):
            return item
    return None


def _empty_draft() -> dict[str, Any]:
    return {
        "suggestedType": "sale",
        "engine": "Heuristic",
        "partyId": None,
        "partyName": None,
        "items": [],
        "amount": None,
        "category": None,
        "discountType": "none",
        "discountValue": 0,
        "date": None,
        "note": "",
    }


def _load_tenant(db: Session, business_id: uuid.UUID) -> tuple[list[Party], list[Product]]:
    parties = list(db.scalars(select(Party).where(Party.business_id == business_id)))
    products = list(db.scalars(select(Product).where(Product.business_id == business_id)))
    return parties, products


def _direction_from_party(matched: Party | None, fallback: str) -> str:
    """A known party's own type is authoritative for sale-vs-purchase."""
    if matched is None:
        return fallback
    return "purchase" if matched.type == "supplier" else "sale"


def draft_from_text(db: Session, business_id: uuid.UUID, text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("Type a command first.")

    parsed = parse_command(text)
    suggested = {
        "PURCHASE_CREATED": "purchase",
        "EXPENSE_ADDED": "expense",
    }.get(parsed.eventType, "sale")

    draft = _empty_draft()
    draft["engine"] = parsed.engine
    draft["date"] = parsed.date
    draft["note"] = text.strip()

    if suggested == "expense":
        draft.update(
            suggestedType="expense",
            amount=parsed.amount,
            category=parsed.category or "General",
        )
        return draft

    parties, products = _load_tenant(db, business_id)
    matched_party = best_match(parties, parsed.party)
    effective = _direction_from_party(matched_party, suggested)

    items: list[dict[str, Any]] = []
    if parsed.allInventory and effective == "sale":
        # "Sell the entire inventory": one line per in-stock product, at its
        # full quantity and selling price. The confirm screen lets them trim.
        in_stock = [p for p in products if p.stock > 0]
        if in_stock:
            items = [
                {
                    "productId": str(p.id),
                    "description": p.name,
                    "quantity": p.stock,
                    "unitPrice": p.selling_price,
                }
                for p in in_stock
            ]
    if not items:
        matched_product = best_match(products, parsed.product)
        qty = int(parsed.quantity) if parsed.quantity and parsed.quantity > 0 else 1
        if matched_product:
            price = (
                matched_product.purchase_price
                if effective == "purchase"
                else matched_product.selling_price
            )
        elif parsed.amount and qty:
            price = round2(parsed.amount / qty)
        else:
            price = 0
        items = [
            {
                "productId": str(matched_product.id) if matched_product else None,
                "description": matched_product.name
                if matched_product
                else (parsed.product or "Item"),
                "quantity": qty,
                "unitPrice": price,
            }
        ]

    draft.update(
        suggestedType=effective,
        partyId=str(matched_party.id) if matched_party else None,
        partyName=matched_party.name if matched_party else parsed.party,
        items=items,
        amount=parsed.amount,
        # Discount only applies to sales; ignored downstream for purchases.
        discountType=parsed.discountType if effective == "sale" else "none",
        discountValue=parsed.discountValue if effective == "sale" else 0,
    )
    return draft


def draft_from_image(
    db: Session, business_id: uuid.UUID, base64_data: str, media_type: str
) -> dict[str, Any]:
    if media_type not in ALLOWED_MEDIA:
        raise ValueError("Unsupported image. Use PNG, JPEG, WebP, or GIF.")

    invoice = parse_invoice_image(base64_data, media_type)
    parties, products = _load_tenant(db, business_id)
    matched_party = best_match(parties, invoice.party)
    effective = _direction_from_party(matched_party, invoice.docType)

    items: list[dict[str, Any]] = []
    for li in invoice.lineItems:
        mp = best_match(products, li.product)
        if li.unitPrice is not None and li.unitPrice > 0:
            price = li.unitPrice
        elif mp:
            price = mp.purchase_price if effective == "purchase" else mp.selling_price
        else:
            price = 0
        items.append(
            {
                "productId": str(mp.id) if mp else None,
                "description": mp.name if mp else li.product,
                "quantity": li.quantity if li.quantity > 0 else 1,
                "unitPrice": price,
            }
        )
    if not items:
        items = [{"productId": None, "description": "Item", "quantity": 1, "unitPrice": 0}]

    status = ai_status()
    draft = _empty_draft()
    draft.update(
        suggestedType=effective,
        engine=(status or {}).get("label", "AI"),
        partyId=str(matched_party.id) if matched_party else None,
        partyName=matched_party.name if matched_party else invoice.party,
        items=items,
        amount=invoice.total,
        discountType=invoice.discountType if effective == "sale" else "none",
        discountValue=invoice.discountValue if effective == "sale" else 0,
        date=invoice.date,
        note="Extracted from image",
    )
    return draft


def publish_draft(
    db: Session,
    business_id: uuid.UUID,
    payload: dict[str, Any],
    actor_id: uuid.UUID | None = None,
) -> dict[str, str]:
    """Run a confirmed draft through the normal domain layer."""
    type_ = payload.get("type") or "sale"
    source = payload.get("source") or "nlp"
    date = parse_date_input(payload.get("date"))

    if type_ == "expense":
        create_expense(
            db,
            business_id,
            ExpenseInput(
                category=payload.get("category") or "General",
                description=payload.get("description") or "",
                amount=float(payload.get("amount") or 0),
                date=date,
                source=source,
            ),
            actor_id,
        )
        return {"ok": "Expense recorded."}

    raw_items = payload.get("items") or []
    items = [
        LineInput(
            productId=i.get("productId"),
            description=i.get("description") or "",
            quantity=int(i.get("quantity") or 0),
            unitPrice=float(i.get("unitPrice") or 0),
        )
        for i in raw_items
    ]
    party_id = payload.get("partyId") or None
    amount_paid = float(payload.get("amountPaid") or 0)
    discount_type = payload.get("discountType") or "none"
    discount_value = float(payload.get("discountValue") or 0)

    if type_ == "purchase":
        pur = purchases_domain.create_purchase(
            db,
            business_id,
            PurchaseInput(
                partyId=party_id,
                items=items,
                amountPaid=amount_paid,
                discountType=discount_type,
                discountValue=discount_value,
                date=date,
                source=source,
            ),
            actor_id,
        )
        return {"ok": f"Purchase {pur.reference_number} created."}

    sale = sales_domain.create_sale(
        db,
        business_id,
        SaleInput(
            partyId=party_id,
            items=items,
            amountPaid=amount_paid,
            discountType=discount_type,
            discountValue=discount_value,
            date=date,
            source=source,
        ),
        actor_id,
    )
    return {"ok": f"Sale {sale.invoice_number} created."}
