"""Hindi and Kannada input, in their own scripts and in Latin letters.

The same note is written four ways — English, Devanagari or Kannada script, and
the romanised form a shopkeeper actually types on a phone — and must come out of
the parser as the same business event. Names and products are checked to survive
in the script they were written in, because that is how they are stored in the
catalogue and how the fuzzy matcher will find them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.ai.lang import detect_scripts, normalize, normalize_digits
from app.ai.nlp import heuristic_parse

HINDI_RICE = "चावल"
KANNADA_RICE = "ಅಕ್ಕಿ"
HINDI_ANITA = "अनीता"
KANNADA_RAMESH = "ರಮೇಶ್"


# ---------------------------------------------------------------------------
# Scripts and digits
# ---------------------------------------------------------------------------
def test_native_digits_become_numbers():
    assert normalize_digits("५") == "5"
    assert normalize_digits("೫೦೦೦") == "5000"
    assert normalize_digits("१२३४५६७८९०") == "1234567890"
    assert normalize_digits("೧೨೩೪೫೬೭೮೯೦") == "1234567890"
    # Latin digits and ordinary text are untouched.
    assert normalize_digits("5 kg rice") == "5 kg rice"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sold 5 kg rice", {"latin"}),
        ("अनीता को बेचा", {"devanagari"}),
        ("ಅನಿತಾಗೆ ಮಾರಿದೆ", {"kannada"}),
        ("5 kg चावल Anita ko becha", {"latin", "devanagari"}),
    ],
)
def test_script_detection(text, expected):
    assert detect_scripts(text) == expected


def test_english_passes_through_unchanged():
    """Normalisation runs on every note, so it must be a no-op for English."""
    english = "sold 5 kg rice to Anita Stores for 700"
    assert normalize(english) == english


# ---------------------------------------------------------------------------
# The same sale, four ways
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("note", "party", "product"),
    [
        ("sold 5 kg rice to Anita Stores", "Anita Stores", "Rice"),
        ("5 kilo chawal Anita ko becha", "Anita", "Chawal"),
        (f"{HINDI_ANITA} को 5 किलो {HINDI_RICE} बेचा", HINDI_ANITA, HINDI_RICE),
        (f"ಅನಿತಾಗೆ ೫ ಕಿಲೋ {KANNADA_RICE} ಮಾರಿದೆ", "ಅನಿತಾ", KANNADA_RICE),
        ("Anita ge 5 kilo akki maride", "Anita", "Akki"),
    ],
)
def test_one_sale_written_five_ways(note, party, product):
    parsed = heuristic_parse(note)
    assert parsed.eventType == "SALE_CREATED", note
    assert parsed.quantity == 5, note
    assert parsed.party == party, note
    assert parsed.product == product, note


@pytest.mark.parametrize(
    "note",
    [
        "bought 10 bags sugar from ABC Suppliers",
        "ABC Suppliers se 10 bori cheeni kharida",
        "ABC Suppliers से 10 बोरी चीनी खरीदा",
        "ABC Suppliers inda 10 chila sakkare kharidiside",
    ],
)
def test_a_purchase_is_recognised_in_every_language(note):
    parsed = heuristic_parse(note)
    assert parsed.eventType == "PURCHASE_CREATED", note
    assert parsed.quantity == 10, note
    assert parsed.party == "Abc Suppliers", note


@pytest.mark.parametrize(
    ("note", "category"),
    [
        ("paid 5000 for rent", "Rent"),
        ("kiraya 5000 kharch", "Rent"),
        ("किराया 5000 खर्च", "Rent"),
        ("ಬಾಡಿಗೆ ೫೦೦೦ ಖರ್ಚು", "Rent"),
        ("ಸಂಬಳ ೧೫೦೦೦ ಖರ್ಚು", "Salary"),
        ("bijli ka kharch 2000", "Electricity"),
    ],
)
def test_expenses_and_their_categories(note, category):
    parsed = heuristic_parse(note)
    assert parsed.eventType == "EXPENSE_ADDED", note
    assert parsed.category == category, note
    assert parsed.amount and parsed.amount > 0, note


@pytest.mark.parametrize(
    "note",
    [
        "Anita wants 3 packets biscuit",
        "Anita ko 3 packet biscuit chahiye",
        "ಅನಿತಾಗೆ ೩ ಪ್ಯಾಕೆಟ್ ಬಿಸ್ಕತ್ ಬೇಕು",
    ],
)
def test_an_order_is_recognised_in_every_language(note):
    assert heuristic_parse(note).eventType == "ORDER_CREATED", note


@pytest.mark.parametrize(
    "note",
    [
        "sell the entire inventory to Anita Stores",
        "Anita ko pura stock bech diya",
        f"ಎಲ್ಲಾ ಸ್ಟಾಕ್ {KANNADA_RAMESH} ಗೆ ಮಾರಿದೆ",
    ],
)
def test_whole_inventory_in_every_language(note):
    parsed = heuristic_parse(note)
    assert parsed.allInventory is True, note
    assert parsed.eventType == "SALE_CREATED", note


@pytest.mark.parametrize(
    "note",
    [
        "sold 2 packets biscuit to Ramesh with 10% discount",
        "Ramesh ko 2 packet biscuit becha 10% chhoot",
        f"{KANNADA_RAMESH} ಗೆ ೨ ಪ್ಯಾಕೆಟ್ ಬಿಸ್ಕತ್ ಮಾರಿದೆ 10% ರಿಯಾಯಿತಿ",
    ],
)
def test_percentage_discount_in_every_language(note):
    parsed = heuristic_parse(note)
    assert parsed.discountType == "percentage", note
    assert parsed.discountValue == 10, note


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


@pytest.mark.parametrize(
    ("note", "days_ago"),
    [
        ("aaj 5 kg rice becha", 0),
        ("आज 5 किलो चावल बेचा", 0),
        ("ಇಂದು ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ", 0),
        ("ninne 5 kg akki maride", 1),
        ("ನಿನ್ನೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ", 1),
        ("parson 5 kg chawal becha", 2),
        ("ಮೊನ್ನೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ", 2),
    ],
)
def test_relative_dates_in_every_language(note, days_ago):
    assert heuristic_parse(note).date == _days_ago(days_ago), note


def test_hindi_kal_means_yesterday_when_something_was_done():
    """कal is both yesterday and tomorrow. A note about what happened is past."""
    assert heuristic_parse("kal 5 kg chawal becha").date == _days_ago(1)
    assert heuristic_parse("कल 5 किलो चावल बेचा").date == _days_ago(1)


def test_hindi_kal_means_tomorrow_when_something_is_wanted():
    """...and a note about what a customer asked for is future."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert heuristic_parse("Anita ko kal 5 kg chawal chahiye").date == tomorrow


# ---------------------------------------------------------------------------
# The things that make this hard
# ---------------------------------------------------------------------------
def test_a_kannada_word_ending_in_the_to_suffix_is_not_split():
    """ಬಾಡಿಗೆ means "rent" and happens to end in ಗೆ, the "to" postposition.
    Splitting it would invent a customer called ಬಾಡಿ."""
    parsed = heuristic_parse("ಬಾಡಿಗೆ ೫೦೦೦ ಖರ್ಚು")
    assert parsed.eventType == "EXPENSE_ADDED"
    assert parsed.category == "Rent"
    assert parsed.party is None


def test_the_product_is_not_swallowed_by_the_party():
    """In "chawal Anita ko" the customer is Anita and the rice is the product;
    both have to survive."""
    parsed = heuristic_parse("5 kilo chawal Anita ko becha")
    assert parsed.party == "Anita"
    assert parsed.product == "Chawal"


def test_a_quantity_is_never_read_as_a_customer():
    """ "5 kg ko" must not produce a customer called "5 kg"."""
    parsed = heuristic_parse("5 kg ko becha")
    assert parsed.party is None or not any(c.isdigit() for c in parsed.party)


def test_shop_names_ending_in_rs_are_not_read_as_money():
    """ "Suppliers 10" contains "rs 10". Traders, Suppliers and Brothers are
    everywhere on Indian shopfronts."""
    assert heuristic_parse("bought 10 bags rice from ABC Suppliers").amount is None
    assert heuristic_parse("sold 5 kg rice to Kumar Traders").amount is None
    # A real amount still reads.
    assert heuristic_parse("sold 5 kg rice to Kumar Traders for rs 700").amount == 700


def test_mixed_script_notes_work():
    """Phones switch keyboards mid-sentence; the note arrives half and half."""
    parsed = heuristic_parse(f"Anita ko 5 kg {HINDI_RICE} becha")
    assert parsed.eventType == "SALE_CREATED"
    assert parsed.party == "Anita"
    assert parsed.product == HINDI_RICE


def test_names_keep_their_script():
    """The catalogue may store the product in Kannada, so translating it here
    would stop the fuzzy matcher ever finding it."""
    parsed = heuristic_parse(f"ಅನಿತಾಗೆ ೫ ಕಿಲೋ {KANNADA_RICE} ಮಾರಿದೆ")
    assert parsed.product == KANNADA_RICE
    assert parsed.party == "ಅನಿತಾ"


def test_normalization_is_idempotent():
    """It runs on every note, including ones already normalised by a retry."""
    once = normalize("Anita ko 5 kilo chawal becha")
    assert normalize(once) == once
