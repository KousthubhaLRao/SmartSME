"""Natural-language parsing for the Smart Input Engine.

An LLM does the work when a key is configured; otherwise a dependency-free
regex parser covers the same fields, so the feature degrades instead of dying.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from .client import extract_json, get_provider
from .lang import DEVANAGARI, KANNADA, normalize

EventType = str  # SALE_CREATED | PURCHASE_CREATED | ORDER_CREATED | EXPENSE_ADDED


@dataclass(slots=True)
class ParsedCommand:
    eventType: EventType = "SALE_CREATED"
    party: str | None = None
    product: str | None = None
    quantity: float | None = None
    amount: float | None = None
    category: str | None = None
    #: True when the note refers to the whole inventory ("sell the entire stock").
    allInventory: bool = False
    discountType: str = "none"
    discountValue: float = 0
    #: Transaction date as YYYY-MM-DD when the note states one, else None.
    date: str | None = None
    #: The provider label that parsed it, or "Heuristic".
    engine: str = "Heuristic"

    def dict(self) -> dict:
        return asdict(self)


SYSTEM = (
    "You extract a single structured business event from an SME shopkeeper's "
    "plain-language note. The note may be in English, Hindi or Kannada, written "
    'either in its own script or in Latin letters ("5 kilo chawal Anita ko '
    'becha", "Anita ge 5 kilo akki maride"), and may mix them in one '
    "sentence. Reply with JSON only, no prose or markdown."
)


def _prompt(text: str, today_iso: str) -> str:
    return f"""Extract one business event from the note and return ONLY a single minified JSON object with exactly these keys:
- eventType: one of "SALE_CREATED" (sold/sale), "PURCHASE_CREATED" (bought/purchased from a supplier), "ORDER_CREATED" (a customer wants/needs something later), "EXPENSE_ADDED" (rent, salary, utilities, fuel, etc.).
- party: the customer or supplier name, or null.
- product: the product name (singular, no unit words like "bags"/"packets"), or null.
- quantity: numeric quantity, or null.
- amount: total money value in rupees if stated, else null.
- category: expense category (e.g. Rent, Utilities) for EXPENSE_ADDED, else null.
- allInventory: true if the note refers to the ENTIRE inventory / all stock / everything in stock (e.g. "sell the entire inventory", "clear out all stock", "sell everything"); otherwise false. When true, leave product and quantity as null.
- discountType: "percentage" if a percentage discount is mentioned (e.g. "10% off", "discount of 10%"), "amount" if a flat money discount is mentioned (e.g. "discount of 300 rupees"), otherwise "none".
- discountValue: the numeric discount, the percent number for "percentage" or the rupee figure for "amount"; 0 when discountType is "none".
- date: the date the transaction happened as "YYYY-MM-DD" if the note states one (e.g. "on 20th August 2026", "yesterday", "3 Sept"); otherwise null. Today is {today_iso}, resolve relative words against it, and assume a bare day+month is the most recent past occurrence.
Language: the note may be English, Hindi or Kannada, in Devanagari, Kannada script or Latin letters, or a mix. Understand all of them. Keep `party` and `product` in the script the note used - do not translate or transliterate them, because they are matched against a catalogue that may itself be in that script. Common verbs: becha/bech diya/ಮಾರಿದೆ/maride mean sold; kharida/ಖರೀದಿಸಿದೆ/kharidiside mean bought; kharch/ಖರ್ಚು/kharchu means an expense; chahiye/ಬೇಕು/beku means a customer wants something. "ko"/"ge"/"ಗೆ" mark the recipient and "se"/"inda"/"ಇಂದ" the supplier, and both come AFTER the name. Hindi "kal" is yesterday for something already done and tomorrow for something wanted.
Use null where a value is unknown. No extra keys, no commentary.

Note: "{text}\""""


def parse_command(text: str) -> ParsedCommand:
    provider = get_provider()
    if provider is not None:
        try:
            raw = provider.complete(
                system=SYSTEM,
                prompt=_prompt(text, _iso_date(datetime.now())),
                max_tokens=1024,
            )
            parsed = extract_json(raw)
            if parsed and parsed.get("eventType"):
                out = _normalize(parsed)
                out.engine = provider.label
                return out
        except Exception as err:
            print(f"[nlp] provider parse failed, falling back to heuristic: {err}")
    out = heuristic_parse(text)
    out.engine = "Heuristic"
    return out


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _num(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normalize(p: dict) -> ParsedCommand:
    discount_type = p.get("discountType")
    if discount_type not in ("amount", "percentage"):
        discount_type = "none"
    discount_value = _num(p.get("discountValue")) or 0
    date = p.get("date")
    return ParsedCommand(
        eventType=p.get("eventType") or "SALE_CREATED",
        party=p.get("party") or None,
        product=p.get("product") or None,
        quantity=_num(p.get("quantity")),
        amount=_num(p.get("amount")),
        category=p.get("category") or None,
        allInventory=bool(p.get("allInventory")),
        discountType=discount_type,
        discountValue=discount_value if discount_value > 0 else 0,
        date=date if isinstance(date, str) and _ISO_RE.match(date) else None,
    )


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
MONTH_INDEX = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"


def _iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _build_date(year: int, month: int, day: int) -> str | None:
    """Reject impossible dates (31 Feb) rather than rolling them over."""
    try:
        return _iso_date(datetime(year, month, day))
    except ValueError:
        return None


def _infer_year(month: int, day: int, today: datetime) -> int:
    """For a bare day+month, pick the most recent occurrence that is not future."""
    year = today.year
    try:
        candidate = datetime(year, month, day)
    except ValueError:
        return year
    return year - 1 if candidate > today else year


def parse_date_phrase(text: str, now: datetime | None = None) -> str | None:
    """Pull a transaction date out of a note. Returns YYYY-MM-DD, or None."""
    now = now or datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    lower = text.lower()

    if re.search(r"\bday before yesterday\b", lower):
        return _iso_date(today - timedelta(days=2))
    if re.search(r"\byesterday\b", lower):
        return _iso_date(today - timedelta(days=1))
    if re.search(r"\btomorrow\b", lower):
        return _iso_date(today + timedelta(days=1))
    if re.search(r"\btoday\b", lower):
        return _iso_date(today)

    # 2026-08-20
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lower)
    if m:
        return _build_date(int(m[1]), int(m[2]), int(m[3]))

    # 20/08/2026 or 20-08-26 (day first, the Indian convention)
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", lower)
    if m:
        year = int(m[3])
        return _build_date(2000 + year if year < 100 else year, int(m[2]), int(m[1]))

    # "20th August 2026", "3 sept", "on 20 aug"
    m = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})[a-z]*\.?(?:,?\s*(\d{{4}}))?\b", lower
    )
    if m:
        day, mon = int(m[1]), MONTH_INDEX[m[2]]
        return _build_date(int(m[3]) if m[3] else _infer_year(mon, day, today), mon, day)

    # "August 20 2026" / "on aug 20" - requires "on" or a year, so a stray
    # "may 10 bags" is not read as a date.
    m = re.search(
        rf"\b(on\s+)?({_MONTHS})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?\b", lower
    )
    if m and (m[1] or m[4]):
        mon, day = MONTH_INDEX[m[2]], int(m[3])
        return _build_date(int(m[4]) if m[4] else _infer_year(mon, day, today), mon, day)

    return None


# ---------------------------------------------------------------------------
# Discounts
# ---------------------------------------------------------------------------
def parse_discount(lower: str) -> tuple[str, float]:
    """Pull a "discount of 10%" / "discount of 300 rupees" clause out of a note."""
    # No trailing \b after the alternation: "%" is a non-word char, so a word
    # boundary can never follow it and "10%" would fail to match.
    pct = re.search(r"(?:discount|off)\D{0,15}?(\d[\d.]*)\s*(?:%|percent|pct)", lower) or re.search(
        r"(\d[\d.]*)\s*(?:%|percent|pct)\s*(?:discount|off)?", lower
    )
    if pct:
        return "percentage", float(pct[1])

    amt = re.search(r"discount\s+of\s+(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)", lower) or re.search(
        r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:discount|off)", lower
    )
    if amt:
        return "amount", float(amt[1].replace(",", ""))

    return "none", 0


# ---------------------------------------------------------------------------
# Heuristic parser
# ---------------------------------------------------------------------------
UNIT_WORDS = re.compile(
    r"\b(bags?|packets?|pkts?|boxes?|box|pcs?|pieces?|units?|kgs?|kg|kilograms?|grams?|g|"
    r"litres?|liters?|ltrs?|l|dozens?|cartons?|of|the)\b",
    re.IGNORECASE,
)


#: Words that can never be part of a party or product name. After
#: normalisation a note can read "to Anita 5 kg rice sold", so the name is no
#: longer guaranteed to sit at the end of the sentence and "$" cannot end it.
#:
#: Only words that cannot appear *inside* a name belong here, and "and" plainly
#: can: it cut "Ram and Sons" down to "Ram", which then matched an entirely
#: different customer called Ramesh, and "salt and pepper" down to "Salt".
#:
#: The whole-inventory wording is matched as a phrase for the same reason. A
#: bare "all" would halve "all purpose flour", whereas "all stock" is not part
#: of anything's name - it is what a note says instead of naming a product.
STOP_WORDS = (
    "for|at|on|worth|each|to|from|tomorrow|today|yesterday|sold|bought|sell|buy|"
    "purchased|expense|spent|wants|order|ordered|discount|off|rs|inr|everything|"
    r"(?:entire|all|whole|complete|full)\s+(?:inventory|stocks?|goods|products?)"
)

#: Left lowercase in the middle of a name, so a new party is created as
#: "Ram and Sons" rather than "Ram And Sons".
_MINOR_WORDS = {"and", "of", "the", "for", "at", "to"}


def _title_case(s: str) -> str:
    words = [w for w in s.lower().split() if w]
    return " ".join(
        w if i and w in _MINOR_WORDS else w[0].upper() + w[1:] for i, w in enumerate(words)
    ).strip()


def heuristic_parse(text: str) -> ParsedCommand:
    """A dependency-free parser for the common shapes.

    Good enough as a starting point: the confirmation screen lets the user
    correct anything before it is published.

    The note is first rewritten into its English shape by `lang.normalize`, so
    Hindi and Kannada — in their own scripts or typed in Latin letters — reach
    the same rules as English. Names and products are left in whatever script
    they were written in, to be matched against the catalogue as-is.
    """
    text = normalize(text)
    lower = text.lower()

    all_inventory = bool(
        re.search(
            r"\b(entire|all|whole|complete|full)\s+(inventory|stock|stocks|goods|products?)\b",
            lower,
        )
        or re.search(r"\b(sell|clear|sold|liquidat\w*)\s+everything\b", lower)
    )
    discount_type, discount_value = parse_discount(lower)
    date = parse_date_phrase(text)

    event_type: EventType = "SALE_CREATED"
    if (
        re.search(r"\b(bought|buy|purchase[ds]?|received|restock(?:ed)?)\b", lower)
        and re.search(r"\bfrom\b", lower)
    ) or re.search(r"\b(bought|buy|purchase[ds]?)\b", lower):
        event_type = "PURCHASE_CREATED"
    elif re.search(r"\b(order(?:ed)?|wants?|need[s]?|requires?|requested)\b", lower):
        event_type = "ORDER_CREATED"
    elif (
        # Strong expense words classify as an expense even with "to <payee>".
        re.search(
            r"\b(rent|salary|wages?|electricity|utilit\w*|fuel|maintenance|internet)\b", lower
        )
        or re.search(r"\b(expense|spent|spend|bill)\b", lower)
        or (re.search(r"\bpaid\b", lower) and not re.search(r"\bto\b", lower))
    ):
        event_type = "EXPENSE_ADDED"
    elif re.search(r"\b(sold|sell|sale)\b", lower):
        event_type = "SALE_CREATED"

    qty_match = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\b", text)
    first_number = float(qty_match[1].replace(",", "")) if qty_match else None

    # "at" is intentionally excluded: it usually marks a unit price
    # ("5 bags at 100 each"), not the total.
    # The word boundary matters: without it "ABC Suppliers 10 bags" matches the
    # "rs" inside "Suppliers" and reads 10 as the money value. Shop names ending
    # in Traders/Suppliers/Brothers are everywhere.
    amt_match = re.search(
        r"(?:₹|\b(?:rs\.?|inr|worth|for|amount))\s*(\d[\d,]*(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    amount = float(amt_match[1].replace(",", "")) if amt_match else None

    party_match = re.search(
        rf"\b(?:to|from)\s+([A-Za-z0-9&.'\s{DEVANAGARI}{KANNADA}]+?)"
        rf"(?=\s+(?:{STOP_WORDS})\b|\s+\d|\s*[.,!?₹]|$)",
        text,
        re.IGNORECASE,
    )
    party = _title_case(party_match[1].strip()) if party_match else None

    if event_type == "EXPENSE_ADDED":
        amount = amount if amount is not None else first_number
        cat_match = re.search(
            rf"\bfor\s+([A-Za-z\s{DEVANAGARI}{KANNADA}]+)", text, re.IGNORECASE
        ) or re.search(
            r"\b(rent|salary|electricity|utilities?|fuel|transport|internet|maintenance|misc\w*)\b",
            text,
            re.IGNORECASE,
        )
        category = _title_case(cat_match[1].strip()) if cat_match else "General"
        return ParsedCommand(
            eventType=event_type,
            party=None,
            product=None,
            quantity=None,
            amount=amount,
            category=category,
            allInventory=False,
            discountType="none",
            discountValue=0,
            date=date,
        )

    # Product = words between the quantity and "to/from", with unit words stripped.
    product: str | None = None
    mid = re.search(
        rf"\b\d[\d,]*(?:\.\d+)?\s+(.*?)(?=\s+(?:{STOP_WORDS})\b|\s*[.,!?]|$)",
        text,
        re.IGNORECASE,
    )
    if mid:
        cleaned = re.sub(r"\s+", " ", UNIT_WORDS.sub(" ", mid[1])).strip()
        product = cleaned or None

    return ParsedCommand(
        eventType=event_type,
        party=party,
        product=_title_case(product) if product else None,
        quantity=first_number,
        amount=amount,
        category=None,
        allInventory=all_inventory,
        discountType=discount_type,
        discountValue=discount_value,
        date=date,
    )
