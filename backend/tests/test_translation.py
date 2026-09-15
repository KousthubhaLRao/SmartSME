"""Reading an order written in a language the catalogue is not written in.

A shop's product list says "Rice Bag 25kg". Its customers say chawal, चावल and
ಅಕ್ಕಿ. Every test here is a sentence somebody would actually type, checked
against the demo catalogue the app seeds, because the whole feature is the gap
between those two vocabularies.
"""

from __future__ import annotations

import pytest

from app.ai.lexicon import concept_of, concepts_in
from app.ai.nlp import heuristic_parse
from app.ai.translit import fold, script_of, skeleton, to_latin
from app.smart_input import best_match


class Row:
    """Stands in for a Party or Product; `best_match` only reads `.name`."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - test output only
        return f"Row({self.name!r})"


#: Exactly what `app/seed.py` creates, so these tests describe the app a person
#: sees on their first run.
PRODUCTS = [
    Row("Rice Bag 25kg"),
    Row("Sugar Packet 1kg"),
    Row("Cooking Oil 1L"),
    Row("Wheat Flour 10kg"),
    Row("Tea Powder 500g"),
]
PARTIES = [Row("Kumar Traders"), Row("Anita Stores"), Row("ABC Suppliers")]


# ---------------------------------------------------------------------------
# Transliteration: names
# ---------------------------------------------------------------------------
def test_scripts_are_recognised():
    assert script_of("अनीता") == "devanagari"
    assert script_of("ಅನಿತಾ") == "kannada"
    assert script_of("Anita") == "latin"
    assert script_of("Anita ಗೆ") == "kannada"


def test_a_name_folds_to_the_same_key_in_every_script():
    """The whole mechanism in one line: three alphabets, one key."""
    assert fold("अनीता") == fold("ಅನಿತಾ") == fold("Anita") == fold("anitha")
    assert fold("कुमार") == fold("ಕುಮಾರ್") == fold("Kumar") == fold("kumaar")


def test_romanised_spelling_variants_fold_together():
    """Nobody agrees how to spell an Indian word in English, and they should
    not have to."""
    assert fold("chawal") == fold("chaval") == fold("chaawal") == fold("चावल")
    assert fold("sakkare") == fold("sakare")
    assert fold("neeru") == fold("niru")


def test_folding_does_not_merge_different_words():
    assert fold("rice") != fold("race")
    assert fold("Kumar") != fold("Kumari")
    assert fold("Anita") != fold("Sunita")


@pytest.mark.parametrize(
    "native,latin",
    [("अनीता", "anita"), ("ಅನಿತಾ", "anita"), ("कुमार", "kumara"), ("ಅಕ್ಕಿ", "akki")],
)
def test_transliteration_produces_readable_latin(native, latin):
    """IAST with the diacritics stripped, which is what `fold` compares."""
    import unicodedata

    plain = "".join(
        c for c in unicodedata.normalize("NFD", to_latin(native)) if not unicodedata.combining(c)
    )
    assert plain.lower() == latin


@pytest.mark.parametrize(
    "query",
    ["Anita", "अनीता", "ಅನಿತಾ", "anitha", "अनीता स्टोर्स", "ಅನಿತಾ ಸ್ಟೋರ್ಸ್", "ANITA STORES"],
)
def test_a_customer_is_found_however_their_name_is_written(query):
    matched = best_match(PARTIES, query)
    assert matched is not None, f"{query} found nobody"
    assert matched.name == "Anita Stores", f"{query} found {matched.name}"


# ---------------------------------------------------------------------------
# Translation: goods
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "word,concept",
    [
        ("चावल", "rice"),
        ("ಅಕ್ಕಿ", "rice"),
        ("chawal", "rice"),
        ("chaval", "rice"),
        ("चीनी", "sugar"),
        ("ಸಕ್ಕರೆ", "sugar"),
        ("shakkar", "sugar"),
        ("तेल", "oil"),
        ("ಎಣ್ಣೆ", "oil"),
        ("आटा", "flour"),
        ("ಹಿಟ್ಟು", "flour"),
        ("चाय", "tea"),
        ("ಚಹಾ", "tea"),
        ("दूध", "milk"),
        ("ಹಾಲು", "milk"),
        ("साबुन", "soap"),
        ("ಸಾಬೂನು", "soap"),
        ("अंडा", "egg"),
        ("ಮೊಟ್ಟೆ", "egg"),
        ("प्याज", "onion"),
        ("ಈರುಳ್ಳಿ", "onion"),
    ],
)
def test_the_lexicon_knows_the_word(word, concept):
    assert concept_of(word) == concept


def test_a_catalogue_name_yields_every_concept_it_mentions():
    """ "Wheat Flour 10kg" is two words a customer might order by."""
    assert concepts_in("Wheat Flour 10kg") >= {"wheat", "flour"}
    assert concepts_in("Rice Bag 25kg") >= {"rice"}
    assert concept_of("something nobody sells") is None


@pytest.mark.parametrize(
    "query,product",
    [
        ("chawal", "Rice Bag 25kg"),
        ("चावल", "Rice Bag 25kg"),
        ("ಅಕ್ಕಿ", "Rice Bag 25kg"),
        ("rice", "Rice Bag 25kg"),
        ("cheeni", "Sugar Packet 1kg"),
        ("चीनी", "Sugar Packet 1kg"),
        ("ಸಕ್ಕರೆ", "Sugar Packet 1kg"),
        ("tel", "Cooking Oil 1L"),
        ("तेल", "Cooking Oil 1L"),
        ("ಎಣ್ಣೆ", "Cooking Oil 1L"),
        ("atta", "Wheat Flour 10kg"),
        ("आटा", "Wheat Flour 10kg"),
        ("गेहूं", "Wheat Flour 10kg"),
        ("ಗೋಧಿ", "Wheat Flour 10kg"),
        ("chai", "Tea Powder 500g"),
        ("चाय", "Tea Powder 500g"),
        ("ಚಹಾ", "Tea Powder 500g"),
    ],
)
def test_a_product_is_found_by_what_it_is_called(query, product):
    matched = best_match(PRODUCTS, query)
    assert matched is not None, f"{query} matched nothing"
    assert matched.name == product, f"{query} matched {matched.name}"


def test_an_unknown_word_matches_nothing_rather_than_guessing():
    assert best_match(PRODUCTS, "helicopter") is None
    assert best_match(PARTIES, "somebody else entirely") is None


# ---------------------------------------------------------------------------
# The three notes from the bug report, end to end
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "note,party,product,quantity",
    [
        (
            "Kumar Traders ko 10 bori chawal becha",
            "Kumar Traders",
            "Rice Bag 25kg",
            10,
        ),
        ("अनीता को 5 किलो चावल बेचा", "Anita Stores", "Rice Bag 25kg", 5),
        ("ಅನಿತಾಗೆ ೪ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ", "Anita Stores", "Rice Bag 25kg", 4),
        ("अनीता स्टोर्स को 5 किलो चावल बेचा", "Anita Stores", "Rice Bag 25kg", 5),
        ("ಅನಿತಾ ಸ್ಟೋರ್ಸ್ ಗೆ 5 ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ", "Anita Stores", "Rice Bag 25kg", 5),
        ("Anita Stores ko 2 packet cheeni becha", "Anita Stores", "Sugar Packet 1kg", 2),
        ("ABC Suppliers se 4 litre tel kharida", "ABC Suppliers", "Cooking Oil 1L", 4),
    ],
)
def test_a_whole_note_reaches_the_right_rows(note, party, product, quantity):
    """Every one of these produced "Custom item" at price zero, with no
    customer, before the catalogue learned to read the other two scripts."""
    parsed = heuristic_parse(note)
    matched_party = best_match(PARTIES, parsed.party)
    matched_product = best_match(PRODUCTS, parsed.product)

    assert matched_party is not None, f"no customer for {note!r} (read {parsed.party!r})"
    assert matched_party.name == party, note
    assert matched_product is not None, f"no product for {note!r} (read {parsed.product!r})"
    assert matched_product.name == product, note
    assert parsed.quantity == quantity, note


# ---------------------------------------------------------------------------
# The guards: looser matching must not resurrect the old wrong-customer bug
# ---------------------------------------------------------------------------
def test_the_wrong_customer_is_still_not_chosen():
    parties = [Row("Ramesh"), Row("Ram and Sons")]
    assert best_match(parties, "Ram").name == "Ram and Sons"
    assert best_match(parties, "Ramesh").name == "Ramesh"
    assert best_match(parties, "Kum") is None


def test_the_consonant_tier_declines_when_it_cannot_choose():
    """Two names with the same consonants and nothing else to go on: the last
    resort is lossy enough to be wrong, so it says nothing instead."""
    ambiguous = [Row("Mehta"), Row("Mahto")]
    assert skeleton("Mehta") == skeleton("Mahto")
    assert best_match(ambiguous, "महतो") is None

    # With only one candidate it is allowed to answer.
    assert best_match([Row("Mehta")], "मेहता").name == "Mehta"


def test_an_english_catalogue_and_an_english_note_are_unaffected():
    """The common case has to stay exactly as it was."""
    assert best_match(PRODUCTS, "Cooking Oil 1L").name == "Cooking Oil 1L"
    assert best_match(PRODUCTS, "cooking oil").name == "Cooking Oil 1L"
    assert best_match(PARTIES, "abc suppliers").name == "ABC Suppliers"
    assert best_match(PARTIES, "Kumar").name == "Kumar Traders"
