"""The expense categories, and nothing else.

Found by the evaluation harness rather than by reading the code: the parser had
no agreed vocabulary. The regex path answered "Electricity", the model answered
"Utilities", both are defensible, and the Expenses page grouped them into two
separate rows of the same chart - so one shop's electricity bill was filed under
two headings depending on which engine happened to read the note.

That is a reporting bug, not a parsing bug, and the fix is a fixed list. The
model is told to choose from it; whatever it answers anyway is mapped onto it;
and anything genuinely unrecognised becomes "General" rather than inventing an
eleventh category nobody will ever look at again.
"""

from __future__ import annotations

#: The only values `category` is ever allowed to take.
#:
#: This is the list the Expenses page already offered, plus Fuel and Taxes,
#: which the note vocabulary can already recognise ("petrol 800", "gst"). The
#: dropdown in `frontend/src/pages/Expenses.tsx` must match it - a category the
#: parser can produce but the form cannot offer is a row nobody can edit back.
CATEGORIES = (
    "Rent",
    "Utilities",
    "Salary",
    "Transport",
    "Fuel",
    "Supplies",
    "Maintenance",
    "Marketing",
    "Taxes",
    "General",
)

#: What people and models actually write, mapped to the list above. The keys are
#: compared lowercased, so only the spelling matters here.
_SYNONYMS = {
    "electricity": "Utilities",
    "electric": "Utilities",
    "power": "Utilities",
    "current": "Utilities",
    "water": "Utilities",
    "internet": "Utilities",
    "phone": "Utilities",
    "bill": "Utilities",
    "utility": "Utilities",
    "wages": "Salary",
    "wage": "Salary",
    "staff": "Salary",
    "salaries": "Salary",
    "petrol": "Fuel",
    "diesel": "Fuel",
    "gas": "Fuel",
    "freight": "Transport",
    "delivery": "Transport",
    "cartage": "Transport",
    "travel": "Transport",
    "lease": "Rent",
    "shop rent": "Rent",
    "stock": "Supplies",
    "goods": "Supplies",
    "inventory": "Supplies",
    "stationery": "Supplies",
    "repair": "Maintenance",
    "repairs": "Maintenance",
    "servicing": "Maintenance",
    "advertising": "Marketing",
    "ads": "Marketing",
    "promotion": "Marketing",
    "tax": "Taxes",
    "gst": "Taxes",
    "other": "General",
    "misc": "General",
    "miscellaneous": "General",
}

_BY_LOWER = {c.lower(): c for c in CATEGORIES}


def canonical_category(value: str | None) -> str:
    """The category this text means, as one of `CATEGORIES`.

    Unknown wording becomes "General" rather than a new heading: a category list
    that grows by one every time somebody phrases an expense differently is not
    a category list.
    """
    if not value:
        return "General"
    text = " ".join(str(value).strip().lower().split())
    if text in _BY_LOWER:
        return _BY_LOWER[text]
    if text in _SYNONYMS:
        return _SYNONYMS[text]
    # "electricity bill", "petrol for van": the head word usually decides.
    for word in text.split():
        if word in _BY_LOWER:
            return _BY_LOWER[word]
        if word in _SYNONYMS:
            return _SYNONYMS[word]
    return "General"


#: For the prompt, so the model is asked for a value from the list rather than
#: for a word of its choosing.
PROMPT_LIST = " | ".join(CATEGORIES)

__all__ = ["CATEGORIES", "PROMPT_LIST", "canonical_category"]
