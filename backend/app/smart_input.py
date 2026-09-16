"""Smart Input: turn a note or an image into a confirmable draft.

The LLM (or the regex fallback) extracts raw fields; this module *grounds* them
against the tenant's own data: fuzzy-matching the party and products, letting a
known party correct the sale-vs-purchase direction, and expanding "the entire
inventory" into one line per in-stock product. Nothing is written here - the
user confirms first, then `publish_draft` runs it through the domain layer.
"""

from __future__ import annotations

import base64
import logging
import re
import unicodedata
import uuid
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai import ocr_space
from .ai.client import ai_status, has_vision
from .ai.lexicon import concepts_in
from .ai.nlp import ParsedCommand, parse_command
from .ai.ocr import ALLOWED_MEDIA, ParsedInvoice, parse_invoice_image
from .ai.slip import parse_slip
from .ai.translit import fold, skeleton, stem
from .core.utils import parse_date_input, round2
from .domain import purchases as purchases_domain
from .domain import sales as sales_domain
from .domain.catalog import create_expense
from .models import Party, Product
from .schemas import ExpenseInput, LineInput, PurchaseInput, SaleInput

log = logging.getLogger("smartsme.smart_input")

T = TypeVar("T", Party, Product)


def _keep(ch: str) -> bool:
    r"""Letters, digits, spaces - and combining marks.

    The marks are the subtle part. In Devanagari and Kannada the vowels of a
    word are written as marks attached to the consonants, and they are Unicode
    category M, which is *not* alphanumeric and so not matched by `\w`. A
    "[^\w\s]" filter therefore deleted them one by one: अनीता came out as
    "अन त", ಅನಿತಾ as "ಅನ ತ".

    That is worse than it sounds, because the damage was symmetrical. Both
    sides of a comparison were mangled the same way, so a name still matched
    itself and a test comparing Kannada to Kannada passed - while nothing could
    ever match across scripts, because the letters transliteration needs had
    already been thrown away before it ever ran.
    """
    return ch.isalnum() or ch.isspace() or unicodedata.category(ch)[0] == "M"


def _norm(s: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace, so "Anita Stores." and
    "ANITA  STORES" compare equal - in every script."""
    cleaned = "".join(ch if _keep(ch) else " " for ch in (s or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokens(s: str | None) -> list[str]:
    """A name as comparable words, whatever alphabet it arrived in.

    `fold` is what makes this cross-script: it transliterates Devanagari and
    Kannada into Latin and then throws away everything writers disagree about,
    so "Anita", "अनीता" and "ಅನಿತಾ" all arrive here as the same token.
    """
    return [stem(fold(t)) for t in _norm(s).split(" ") if fold(t)]


def _run_of(haystack: list[str], needle: list[str]) -> bool:
    """Does `needle` appear in `haystack` as consecutive whole words?"""
    if not needle or len(needle) > len(haystack):
        return False
    if len(needle) == 1 and len(needle[0]) < 3:
        # "Al" would otherwise claim every name containing the word.
        return False
    return any(
        haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1)
    )


def _only(matches: list[T]) -> T | None:
    """The single match, or nothing.

    Used for the guessing tiers. When a rule is loose enough to hit two
    catalogue entries it is too loose to pick between them, and picking the
    first is how a sale ends up billed to the wrong customer - so it declines
    and leaves the dropdown on the confirm screen to whoever is reading it.
    """
    return matches[0] if len(matches) == 1 else None


def best_match(items: list[T], query: str | None) -> T | None:
    """Find the catalogue row a phrase is talking about, in any of three
    scripts, in five passes from certain to merely likely.

    1. the same name, exactly
    2. the same words, allowing for script and spelling ("अनीता" / "Anita")
    3. the same thing, by meaning ("चावल" / "chawal" / "ಅಕ್ಕಿ" -> rice ->
       "Rice Bag 25kg") - `lexicon.py` supplies the vocabulary
    4. the same words in a different order
    5. the same consonants, and only when exactly one row has them - the last
       resort for what transliteration cannot recover, like स्टोर्स ("storsa")
       against a catalogue that says "Stores"

    Every comparison is on whole words. Plain substring matching looks the same
    on the examples that motivate it and is quietly wrong in between: "Ram"
    resolved to "Ramesh", so a sale to Ram and Sons was billed to a different
    customer entirely. A name has to match something the other name actually
    says, not a run of letters inside one of its words.
    """
    if not query:
        return None
    needle = _norm(query)
    if not needle:
        return None

    # 1. The same name.
    for item in items:
        if _norm(item.name) == needle:
            return item

    # 2. The same words, once script and spelling are folded away.
    needle_tokens = _tokens(needle)
    for item in items:
        item_tokens = _tokens(item.name)
        if _run_of(item_tokens, needle_tokens) or _run_of(needle_tokens, item_tokens):
            return item

    # 3. The same goods by meaning. Only products are named by what they are; a
    #    person called Anita is not an instance of anything.
    wanted = concepts_in(query)
    if wanted:
        by_concept = [item for item in items if wanted & concepts_in(item.name)]
        if by_concept:
            # Several rice products is normal; the first is as good a guess as
            # any, and the confirm screen shows which one was chosen.
            return by_concept[0]

    # 4. The same words, in any order.
    for item in items:
        item_tokens = _tokens(item.name)
        if not item_tokens:
            continue
        short, long_set = (
            (needle_tokens, set(item_tokens))
            if len(needle_tokens) <= len(item_tokens)
            else (item_tokens, set(needle_tokens))
        )
        if short and all(t in long_set for t in short):
            return item

    # 5. The same consonants - lossy, so only when nothing else could be meant.
    needle_bones = [skeleton(t) for t in needle_tokens if len(skeleton(t)) > 1]
    if needle_bones:
        candidates = []
        for item in items:
            bones = [skeleton(t) for t in _tokens(item.name) if len(skeleton(t)) > 1]
            if _run_of(bones, needle_bones) or _run_of(needle_bones, bones):
                candidates.append(item)
        return _only(candidates)
    return None


def phone_key(value: str | None) -> str:
    """The comparable part of a phone number.

    Everything people vary is discarded - spaces, dashes, brackets, a +91, a
    leading 0 - and the last ten digits are kept, because that is the part that
    identifies an Indian subscriber however it was written down.
    """
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def party_by_phone(parties: list[Party], phone: str | None) -> Party | None:
    """The one party with this number, or None.

    Tried before any name matching, because it is the only signal on an order
    slip that is exact. If two parties somehow share a number there is nothing
    to choose between them, so it declines rather than guesses.
    """
    key = phone_key(phone)
    if len(key) < 10:
        return None
    hits = [p for p in parties if phone_key(getattr(p, "phone", None)) == key]
    return hits[0] if len(hits) == 1 else None


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


def ground_text(
    parsed: ParsedCommand, parties: list, products: list, note: str = ""
) -> dict[str, Any]:
    """Turn a parsed note into a draft against a given catalogue.

    Split out from `draft_from_text` so the grounding step can be run against a
    catalogue that did not come from the database - which is what the accuracy
    harness in `eval/` needs. Measuring a pipeline through a different code path
    than the one that ships measures the wrong pipeline, so the evaluation calls
    this, and so does the app.
    """
    suggested = {
        "PURCHASE_CREATED": "purchase",
        "EXPENSE_ADDED": "expense",
    }.get(parsed.eventType, "sale")

    draft = _empty_draft()
    draft["engine"] = parsed.engine
    draft["date"] = parsed.date
    draft["note"] = note.strip()

    if suggested == "expense":
        draft.update(
            suggestedType="expense",
            amount=parsed.amount,
            category=parsed.category or "General",
        )
        return draft

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
        # One draft line per item the note named. A note is a list - "20 tea
        # packets, 40 rice bags and 10 sugar packets" is three things - and
        # building a single line here dropped the rest however well they were
        # parsed.
        for line in parsed.lineItems:
            matched_product = best_match(products, line.product)
            qty = int(line.quantity) if line.quantity and line.quantity > 0 else 1
            if matched_product:
                price = (
                    matched_product.purchase_price
                    if effective == "purchase"
                    else matched_product.selling_price
                )
            elif parsed.amount and qty and len(parsed.lineItems) == 1:
                # A stated total only divides cleanly when there is one line to
                # divide it into; with several it belongs to the order, not to
                # any one of them.
                price = round2(parsed.amount / qty)
            else:
                price = 0
            items.append(
                {
                    "productId": str(matched_product.id) if matched_product else None,
                    "description": matched_product.name if matched_product else line.product,
                    "quantity": qty,
                    "unitPrice": price,
                }
            )

    if not items:
        # Nothing nameable in the note; the confirm screen starts from a blank
        # line rather than from nothing.
        items = [{"productId": None, "description": "Item", "quantity": 1, "unitPrice": 0}]

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


def draft_from_text(db: Session, business_id: uuid.UUID, text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("Type a command first.")
    parties, products = _load_tenant(db, business_id)
    return ground_text(parse_command(text), parties, products, note=text)


def read_image(base64_data: str, media_type: str) -> tuple[ParsedInvoice, str]:
    """Read an order slip with the best engine configured, and say which one.

    Two engines, in order of what they can do rather than what they cost,
    because both free tiers cost nothing:

    1. **A vision model.** Reads handwriting, and - the reason it is first -
       can be told to ignore a line that was crossed out. Corrections in place
       are ordinary on a handwritten slip, and every one of them is an item
       that must not be recorded.
    2. **OCR.space.** Free, and on real slips it reads the handwriting
       accurately. What it cannot do is see a strikethrough: that information
       is not in a stream of characters, so a cancelled line arrives looking
       exactly like a live one.

    Neither writes anything. The draft goes to the confirm screen, which is
    where the second engine's blind spot is meant to be caught.
    """
    if has_vision():
        try:
            return parse_invoice_image(base64_data, media_type), "vision"
        except Exception as err:
            # A provider that is down should not take the feature with it when a
            # working one is configured. The draft is labelled with whichever
            # engine produced it, so the person reviewing knows a crossed-out
            # line could be sitting in it - which is the only thing the second
            # engine is worse at.
            if not ocr_space.enabled():
                raise
            log.warning("vision OCR failed (%s); falling back to OCR.space", err)

    if ocr_space.enabled():
        try:
            text = ocr_space.read_text(base64.b64decode(base64_data))
        except ocr_space.OcrUnavailable as err:
            # Its message names the cause - no key, a refused image, an
            # unreachable host - and all of them are things the person holding
            # the phone can act on, so it reaches them rather than becoming a
            # bare 502.
            raise ValueError(str(err)) from err
        if not text.strip():
            raise ValueError("No text could be read from that image.")
        return parse_slip(text), "ocr.space"

    raise ValueError(
        "Reading an image needs either an AI key that can see images "
        "(GOOGLE_API_KEY is free) or OCR_SPACE_API_KEY. Set one in backend/.env, "
        "or type the order into Smart Input instead."
    )


def draft_from_image(
    db: Session, business_id: uuid.UUID, base64_data: str, media_type: str
) -> dict[str, Any]:
    if media_type not in ALLOWED_MEDIA:
        raise ValueError("Unsupported image. Use PNG, JPEG, WebP, or GIF.")

    invoice, engine = read_image(base64_data, media_type)
    parties, products = _load_tenant(db, business_id)
    # The phone number first: it is the only exact key on an order slip, and
    # the names on one ("S. Khan", "Priya M.") are the hardest kind to match.
    matched_party = party_by_phone(parties, invoice.phone) or best_match(parties, invoice.party)
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

    # The engine is named on the draft because it matters to whoever reviews it:
    # OCR.space cannot see a crossed-out line, so those items deserve a closer
    # read than the ones a vision model produced.
    status = ai_status()
    label = (status or {}).get("label", "AI") if engine == "vision" else "OCR.space"
    draft = _empty_draft()
    draft.update(
        suggestedType=effective,
        engine=label,
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
    """Run a confirmed draft through the normal domain layer.

    Accepts either shape: the explicit `{"type": ...}` the Smart Input form
    builds, or a draft straight from `draft_from_text`, which names the same
    field `suggestedType`. Taking only the first silently turned every emailed
    purchase into a sale.
    """
    type_ = payload.get("type") or payload.get("suggestedType") or "sale"
    source = payload.get("source") or "nlp"
    date = parse_date_input(payload.get("date"))

    if type_ == "expense":
        create_expense(
            db,
            business_id,
            ExpenseInput(
                category=payload.get("category") or "General",
                # A draft keeps the original message in `note`; the form
                # sends a `description`. Either can name the expense.
                description=payload.get("description") or payload.get("note") or "",
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
