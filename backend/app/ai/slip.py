"""Turning the text off an order slip into the same structure the vision path returns.

`ocr_space.read_text` gives back the words on the paper and nothing else. A
handwritten order slip has a shape, though, and it is a remarkably consistent
one:

    Name: Latha
    Ph no: 9880011223
    Order:
    5 kgs Dal
    10 kgs Rice
    2 kgs Salt

So this reads that shape - a name, a phone number, then one item per line as
"<quantity> <unit> <product>" - and produces the same `ParsedInvoice` a vision
model would, which is what lets both paths share everything downstream.

Two corrections are applied, both measured against real slips rather than
imagined:

* **"I" is a 1.** Every OCR engine confuses a handwritten 1 with a capital I,
  and "I bag White Cement" is not an order for an unknown quantity.
* **A tab is a line break.** The engine sometimes merges two short lines onto
  one row with a tab between them, which would otherwise glue two items into
  one nonsense product.

What it cannot do is notice that a line was crossed out - that information
never reaches the text. A slip that has been corrected in place needs the
vision path, or a person at the confirm screen.
"""

from __future__ import annotations

import re

from .ocr import ParsedInvoice, ParsedInvoiceLine

#: Words that measure rather than name. Anything here sitting between the
#: quantity and the product is a unit and not part of what was ordered.
UNITS = {
    "unit",
    "units",
    "no",
    "nos",
    "kg",
    "kgs",
    "kilo",
    "kilos",
    "kilogram",
    "kilograms",
    "g",
    "gm",
    "gms",
    "gram",
    "grams",
    "l",
    "ltr",
    "ltrs",
    "litre",
    "litres",
    "liter",
    "liters",
    "ml",
    "bag",
    "bags",
    "box",
    "boxes",
    "carton",
    "cartons",
    "packet",
    "packets",
    "pkt",
    "pkts",
    "pack",
    "packs",
    "pc",
    "pcs",
    "piece",
    "pieces",
    "dozen",
    "dozens",
    "drum",
    "drums",
    "can",
    "cans",
    "tin",
    "tins",
    "jar",
    "jars",
    "bottle",
    "bottles",
    "tube",
    "tubes",
    "roll",
    "rolls",
    "sheet",
    "sheets",
    "m",
    "mtr",
    "mtrs",
    "meter",
    "meters",
    "metre",
    "metres",
    "ft",
    "feet",
    "pair",
    "pairs",
    "set",
    "sets",
    "bundle",
    "bundles",
}

#: The line that says who wrote the slip.
_NAME = re.compile(r"^\s*name\s*[:;.\-]\s*(.+)$", re.IGNORECASE)

#: Phone, however they abbreviate it.
_PHONE = re.compile(
    r"^\s*(?:ph|phone|mob|mobile|contact|cell)\s*(?:no\.?)?\s*[:;.\-]\s*(.+)$", re.IGNORECASE
)

#: "Order:" - sometimes with the first item on the same line.
_ORDER = re.compile(r"^\s*order\s*[:;.\-]\s*(.*)$", re.IGNORECASE)

#: "<quantity> <unit?> <product>"
_ITEM = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s+(.*)$")

#: A handwritten 1 read as a letter, at the start of an item.
_ONE = re.compile(r"^\s*[Il]\s+(?=\S)")


def _lines(text: str) -> list[str]:
    """One logical line per entry, tabs included - the engine uses them to
    merge two short rows it decided were columns."""
    flat = text.replace("\t", "\n")
    return [line.strip() for line in flat.splitlines() if line.strip()]


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _split_item(line: str) -> ParsedInvoiceLine | None:
    """One order line, or None if it is not one."""
    line = _ONE.sub("1 ", line.strip())
    line = line.strip(" .,;:-")
    match = _ITEM.match(line)
    if not match:
        return None

    try:
        quantity = int(float(match[1].replace(",", ".")))
    except ValueError:
        return None
    if quantity <= 0:
        return None

    rest = match[2].strip(" .,;:-")
    words = rest.split()
    # Drop a leading unit word; "5 kgs Dal" is five of Dal, not five kilogram-dals.
    if words and words[0].lower().strip(".") in UNITS and len(words) > 1:
        words = words[1:]
    product = " ".join(words).strip(" .,;:-")
    if not product:
        return None
    return ParsedInvoiceLine(product=product, quantity=quantity)


def parse_slip(text: str) -> ParsedInvoice:
    """Read an order slip's text. Never raises: an unreadable slip becomes an
    empty invoice, which the Inbox shows as "could not read" rather than
    losing."""
    party: str | None = None
    phone: str | None = None
    items: list[ParsedInvoiceLine] = []
    in_order = False

    for line in _lines(text):
        if (found := _NAME.match(line)) and party is None:
            party = found[1].strip(" .,;:-") or None
            continue
        if (found := _PHONE.match(line)) and phone is None:
            digits = _digits(found[1])
            phone = digits or None
            continue
        if found := _ORDER.match(line):
            in_order = True
            # "Order: 3 units Product A" carries the first item already.
            if (remainder := found[1].strip()) and (item := _split_item(remainder)):
                items.append(item)
            continue

        # Before "Order:" there can be a heading or a date; after it, items.
        # A quantity-led line is an item wherever it appears, because not every
        # slip bothers with the word "Order" at all.
        if item := _split_item(line):
            items.append(item)
            in_order = True
        elif not in_order and party is None and line:
            # An unlabelled first line is usually the customer's name.
            party = line.strip(" .,;:-")

    return ParsedInvoice(party=party, phone=phone, docType="sale", lineItems=items)


__all__ = ["UNITS", "parse_slip"]
