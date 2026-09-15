"""Image OCR: invoice / order slip / WhatsApp screenshot -> structured data.

Extracts the same fields as the text parser (party, lines, total, date and
discount) so both Smart Input paths stay at feature parity. There is no offline
fallback: OCR needs a vision-capable provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from .client import AiImage, extract_json, get_provider

ALLOWED_MEDIA = ("image/png", "image/jpeg", "image/webp", "image/gif")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(slots=True)
class ParsedInvoiceLine:
    product: str
    quantity: int
    unitPrice: float | None = None


@dataclass(slots=True)
class ParsedInvoice:
    party: str | None = None
    #: The number written on the slip. Worth more than the name: "S. Khan" and
    #: "Priya M." are exactly what fuzzy name matching is worst at, and a phone
    #: number is an exact key.
    phone: str | None = None
    docType: str = "sale"  # sale | purchase
    lineItems: list[ParsedInvoiceLine] = field(default_factory=list)
    total: float | None = None
    date: str | None = None
    discountType: str = "none"
    discountValue: float = 0


SYSTEM = (
    "You read an SME invoice, order slip, or handwritten note from an image and "
    "return structured data. Reply with JSON only, no prose or markdown."
)


def _prompt(today_iso: str) -> str:
    return f"""Extract this invoice / order slip / WhatsApp screenshot into structured data.
Return ONLY a single minified JSON object with exactly these keys:
- party: the other business or person named, or null.
- phone: the customer's phone number as written, digits only, or null.
- docType: "purchase" if this is a bill we received from a supplier, else "sale".
- lineItems: an array of objects, each {{ "product": string, "quantity": number, "unitPrice": number-or-null }}.
- total: the document total as a number, or null.
- date: the date printed on the document as "YYYY-MM-DD", or null if none is shown. Today is {today_iso}; resolve relative wording against it, and read day-first formats (20/08/2026 means 20 August 2026).
- discountType: "percentage" if a percentage discount is shown, "amount" if a flat money discount is shown, otherwise "none".
- discountValue: the numeric discount (the percent number, or the money figure); 0 when discountType is "none".
Include every line item.
IMPORTANT - handwritten slips get corrected in place, and a correction is not an order:
- IGNORE any text that is crossed out, struck through, scribbled over or otherwise cancelled. It was withdrawn by the person who wrote it. Do not include it as a line item, and do not use it as a product name.
- If a line reads like "5 bags <crossed out word> Atta", the product is what SURVIVES the correction ("Atta"), not the words that were struck out.
- If the same item appears twice because the first attempt was crossed out, count it ONCE.
Use null where a value is unknown. No extra keys, no commentary."""


def parse_invoice_image(base64_data: str, media_type: str) -> ParsedInvoice:
    provider = get_provider(vision=True)
    if provider is None or not provider.vision:
        raise ValueError(
            "Image OCR needs an AI provider that can read images. Set an API key "
            "(ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY), or use text input instead."
        )

    today_iso = datetime.now().strftime("%Y-%m-%d")
    raw = provider.complete(
        system=SYSTEM,
        prompt=_prompt(today_iso),
        image=AiImage(base64=base64_data, media_type=media_type),
        max_tokens=2048,
    )

    parsed = extract_json(raw)
    if not parsed:
        raise ValueError("Could not read a structured invoice from that image.")

    lines: list[ParsedInvoiceLine] = []
    for li in parsed.get("lineItems") or []:
        if not isinstance(li, dict):
            continue
        try:
            qty = int(float(li.get("quantity") or 1))
        except (TypeError, ValueError):
            qty = 1
        unit_price = li.get("unitPrice")
        try:
            unit_price = float(unit_price) if unit_price is not None else None
        except (TypeError, ValueError):
            unit_price = None
        lines.append(
            ParsedInvoiceLine(
                product=str(li.get("product") or "Item"),
                quantity=qty if qty > 0 else 1,
                unitPrice=unit_price,
            )
        )

    total = parsed.get("total")
    try:
        total = float(total) if total is not None else None
    except (TypeError, ValueError):
        total = None

    discount_type = parsed.get("discountType")
    if discount_type not in ("amount", "percentage"):
        discount_type = "none"
    try:
        discount_value = float(parsed.get("discountValue") or 0)
    except (TypeError, ValueError):
        discount_value = 0
    date = parsed.get("date")

    phone = parsed.get("phone")
    phone = re.sub(r"\D", "", str(phone)) if phone else None

    return ParsedInvoice(
        party=parsed.get("party") or None,
        phone=phone or None,
        docType="purchase" if parsed.get("docType") == "purchase" else "sale",
        lineItems=lines,
        total=total,
        date=date if isinstance(date, str) and _ISO_RE.match(date) else None,
        discountType=discount_type,
        discountValue=discount_value if discount_value > 0 else 0,
    )
