"""Multilingual input for the Smart Input parser.

Shopkeepers do not write in one language. A note can arrive as English, as Hindi
or Kannada in their own scripts, as either of those typed in Latin letters
("5 kilo chawal Anita ko becha"), or as a mix of all of them in one sentence.

Rather than teaching every regex in `nlp.py` four vocabularies, this module
normalises a note *into* the English shape that parser already understands:

    "ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ"  ->  "to ಅನಿತಾ 5 kg ಅಕ್ಕಿ sold"

Two things are deliberately preserved:

* **Names and products stay in their original script.** Only known keywords are
  rewritten, so "ಅಕ್ಕಿ" survives to be matched against the catalogue, where it
  may well be stored in Kannada too.
* **Word order is repaired, not just vocabulary.** Hindi and Kannada mark the
  recipient with a postposition after the name ("Anita ko", "ಅನಿತಾಗೆ") where
  English uses a preposition before it. Without moving those, the party would
  never be found.

This is the fallback path. When an AI provider is configured it handles the
language directly, and the prompt tells it so; this keeps the feature working,
in every language, when no key is set.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Scripts and digits
# ---------------------------------------------------------------------------
DEVANAGARI = "ऀ-ॿ"
KANNADA = "ಀ-೿"

#: Letters that may appear in a name or product, in any of the three scripts.
NAME_CHARS = rf"A-Za-z0-9&.'\s{DEVANAGARI}{KANNADA}"

_DIGIT_MAP = {
    **{chr(0x0966 + i): str(i) for i in range(10)},  # Devanagari ०-९
    **{chr(0x0CE6 + i): str(i) for i in range(10)},  # Kannada ೦-೯
}


def detect_scripts(text: str) -> set[str]:
    """Which writing systems appear in the note. Used for reporting, and to
    tell the UI what it is looking at."""
    found: set[str] = set()
    for ch in text:
        code = ord(ch)
        if 0x0900 <= code <= 0x097F:
            found.add("devanagari")
        elif 0x0C80 <= code <= 0x0CFF:
            found.add("kannada")
        elif ch.isalpha() and code < 0x0250:
            found.add("latin")
    return found


def normalize_digits(text: str) -> str:
    """೫ -> 5, ५ -> 5. Quantities and money are useless otherwise."""
    return "".join(_DIGIT_MAP.get(ch, ch) for ch in text)


# ---------------------------------------------------------------------------
# Vocabulary
#
# Each entry rewrites one concept into the English word `nlp.py` looks for.
# Longer forms come first so "bech diya" is not half-matched by "bech".
# ---------------------------------------------------------------------------
def _alt(*words: str) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


VOCABULARY: list[tuple[str, str]] = [
    # -- sold -------------------------------------------------------------
    (
        _alt(
            # Hindi
            "बेच दिया",
            "बेचा",
            "बेची",
            "बेचे",
            "बेचकर",
            "बिक्री",
            "बेच",
            "bech diya",
            "bech diye",
            "becha",
            "bechi",
            "beche",
            "bechkar",
            "bikri",
            "bech",
            # Kannada
            "ಮಾರಿದ್ದೇನೆ",
            "ಮಾರಾಟ",
            "ಮಾರಿದೆ",
            "ಮಾರಿದರು",
            "ಮಾರಿ",
            "maaridhe",
            "maarideने",
            "maridhe",
            "maaride",
            "maarata",
            "maratha",
            "maride",
            "maari",
        ),
        "sold",
    ),
    # -- bought -----------------------------------------------------------
    (
        _alt(
            "खरीदा",
            "ख़रीदा",
            "खरीदी",
            "ख़रीदी",
            "खरीद",
            "मंगाया",
            "मँगाया",
            "लिया",
            "khareeda",
            "kharida",
            "khareedi",
            "kharidi",
            "kharid",
            "mangaya",
            "mangvaya",
            "ಖರೀದಿಸಿದೆ",
            "ಖರೀದಿಸಿ",
            "ಖರೀದಿ",
            "ತಂದೆ",
            "kharidiside",
            "kharidisi",
            "kharidi",
            "khareedi",
            "tande",
            "tandhe",
        ),
        "bought",
    ),
    # -- expense ----------------------------------------------------------
    (
        _alt(
            "खर्चा",
            "ख़र्चा",
            "खर्च",
            "ख़र्च",
            "भुगतान",
            "kharcha",
            "kharche",
            "kharch",
            "bhugtan",
            "ಖರ್ಚು",
            "ಖರ್ಚಾಯಿತು",
            "kharchu",
            "kharchaayitu",
            "kharchayitu",
        ),
        "expense",
    ),
    # -- order / wants ----------------------------------------------------
    (
        _alt(
            "चाहिए",
            "चाहिये",
            "ज़रूरत",
            "जरूरत",
            "माँगा",
            "मांगा",
            "ऑर्डर",
            "chahiye",
            "chaahiye",
            "zarurat",
            "jarurat",
            "manga",
            "maanga",
            "ಬೇಕು",
            "ಬೇಕಿದೆ",
            "ಆರ್ಡರ್",
            "beku",
            "bekku",
            "bekide",
        ),
        "wants",
    ),
    # -- expense categories ----------------------------------------------
    (_alt("किराया", "किराये", "kiraya", "kiraaya", "ಬಾಡಿಗೆ", "badige", "baadige"), "rent"),
    (
        _alt(
            "वेतन",
            "तनख्वाह",
            "तनख़्वाह",
            "vetan",
            "tankhwah",
            "tankhah",
            "ಸಂಬಳ",
            "sambala",
            "sambhala",
            "sambalaa",
        ),
        "salary",
    ),
    (
        _alt("बिजली", "बिजली बिल", "bijli", "ಕರೆಂಟ್", "ವಿದ್ಯುತ್", "karent", "vidyut"),
        "electricity",
    ),
    (_alt("ईंधन", "पेट्रोल", "डीजल", "petrol", "diesel", "ಪೆಟ್ರೋಲ್", "ಡೀಸೆಲ್"), "fuel"),
    (_alt("भाड़ा", "bhada", "bhaada", "ಸಾಗಣೆ", "sagane", "saagane"), "transport"),
    # -- dates -------------------------------------------------------------
    (_alt("आज", "aaj", "ಇಂದು", "ಇವತ್ತು", "indu", "ivattu", "ivatthu"), "today"),
    (_alt("परसों", "parson", "parsoon", "ಮೊನ್ನೆ", "monne"), "day before yesterday"),
    (_alt("ನಿನ್ನೆ", "ninne", "ninneya"), "yesterday"),
    (_alt("ನಾಳೆ", "naale", "nale", "naalé"), "tomorrow"),
    # कल / kal is both yesterday and tomorrow in Hindi; resolved below, where
    # the tense of the rest of the note can be taken into account.
    # -- discount ----------------------------------------------------------
    (
        _alt(
            "छूट",
            "छुट",
            "कटौती",
            "डिस्काउंट",
            "chhoot",
            "chhut",
            "chhoot",
            "katauti",
            "ರಿಯಾಯಿತಿ",
            "ಡಿಸ್ಕೌಂಟ್",
            "riyayiti",
            "riyaayiti",
        ),
        "discount",
    ),
    # -- money -------------------------------------------------------------
    (
        _alt(
            "रुपये",
            "रुपए",
            "रूपये",
            "रुपया",
            "रु",
            "rupaye",
            "rupaiya",
            "rupaya",
            "rupay",
            "ರೂಪಾಯಿ",
            "ರೂಪಾಯಿಗಳು",
            "ರೂ",
            "rupayi",
            "rupaayi",
            "rupai",
        ),
        "rs",
    ),
    # -- whole inventory ---------------------------------------------------
    (
        _alt(
            "पूरा स्टॉक",
            "सारा माल",
            "सारा स्टॉक",
            "पूरी दुकान",
            "सब माल",
            "pura stock",
            "poora stock",
            "saara maal",
            "sara maal",
            "sab maal",
            "ಎಲ್ಲಾ ಸ್ಟಾಕ್",
            "ಪೂರ್ತಿ ಸ್ಟಾಕ್",
            "ಎಲ್ಲಾ ಸರಕು",
            "ella stock",
            "ellaa stock",
            "poorti stock",
            "purti stock",
            "ella saraku",
        ),
        "entire stock",
    ),
    # -- units -------------------------------------------------------------
    (_alt("किलोग्राम", "किलो", "किग्रा", "kilo", "ಕಿಲೋ", "ಕೆಜಿ", "keji"), "kg"),
    (_alt("ग्राम", "gram", "ಗ್ರಾಂ"), "g"),
    (_alt("लीटर", "litre", "ಲೀಟರ್", "liter"), "litre"),
    (_alt("पैकेट", "packet", "ಪ್ಯಾಕೆಟ್", "paket"), "packet"),
    (_alt("बोरी", "bori", "boree", "ಚೀಲ", "cheela", "chila"), "bag"),
    (_alt("डिब्बा", "डब्बा", "dibba", "dabba", "ಡಬ್ಬ", "dabba"), "box"),
    (_alt("दर्जन", "darjan", "ಡಜನ್", "dajan"), "dozen"),
    (_alt("पीस", "ಪೀಸ್", "pcs"), "pieces"),
]

_VOCAB_RE = [
    (
        re.compile(
            rf"(?<![\w{DEVANAGARI}{KANNADA}])(?:{pattern})(?![\w{DEVANAGARI}{KANNADA}])",
            re.IGNORECASE,
        ),
        english,
    )
    for pattern, english in VOCABULARY
]

# ---------------------------------------------------------------------------
# Postpositions
#
# "Anita ko" -> "to Anita". The captured name is rejected if it looks like a
# number or a word we have already rewritten, so "5 kg ko" cannot be read as a
# customer called "5 kg".
# ---------------------------------------------------------------------------
_NOT_A_NAME = {
    "sold",
    "bought",
    "expense",
    "wants",
    "rs",
    "kg",
    "g",
    "litre",
    "packet",
    "bag",
    "box",
    "dozen",
    "pieces",
    "discount",
    "today",
    "yesterday",
    "tomorrow",
    "stock",
    "entire",
    "rent",
    "salary",
    "electricity",
    "fuel",
    "transport",
    "and",
    "the",
    "for",
    "at",
    "of",
}

_TO_WORDS = ("को", "ko", "ಗೆ", "ge", "ಕ್ಕೆ", "kke")
_FROM_WORDS = ("से", "se", "ಇಂದ", "inda", "ind", "ಕಡೆಯಿಂದ", "kadeyinda")


def _postposition_re(words: tuple[str, ...]) -> re.Pattern[str]:
    #: One or two words before the postposition, which is as much of a shop
    #: name as these notes ever carry.
    name = rf"[A-Za-z{DEVANAGARI}{KANNADA}][\w{DEVANAGARI}{KANNADA}.&']*"
    return re.compile(
        rf"(?<![\w{DEVANAGARI}{KANNADA}])({name}(?:\s+{name})?)\s+(?:{_alt(*words)})"
        rf"(?![\w{DEVANAGARI}{KANNADA}])",
        re.IGNORECASE,
    )


_TO_RE = _postposition_re(_TO_WORDS)
_FROM_RE = _postposition_re(_FROM_WORDS)

#: Kannada glues the postposition onto the name: "ಅನಿತಾಗೆ" is "to Anita". Only
#: the native script is handled here — splitting a romanised "Anitage" would be
#: guesswork.
_KANNADA_SUFFIX_TO = re.compile(rf"(?<![\w{KANNADA}])([{KANNADA}]{{3,}})(ಗೆ|ಕ್ಕೆ)(?![\w{KANNADA}])")
_KANNADA_SUFFIX_FROM = re.compile(rf"(?<![\w{KANNADA}])([{KANNADA}]{{3,}})(ಇಂದ)(?![\w{KANNADA}])")


#: Unit words, including the plain English plurals a note may already use. A
#: word sitting right after one of these is what was sold, not who it went to.
_UNIT_LEAD_IN = {
    "kg",
    "kgs",
    "g",
    "gram",
    "grams",
    "litre",
    "litres",
    "liter",
    "liters",
    "ltr",
    "packet",
    "packets",
    "pkt",
    "pkts",
    "bag",
    "bags",
    "box",
    "boxes",
    "carton",
    "cartons",
    "dozen",
    "dozens",
    "piece",
    "pieces",
    "pcs",
    "unit",
    "units",
}

_DEVANAGARI_RE = re.compile(f"[{DEVANAGARI}]")
_KANNADA_RE = re.compile(f"[{KANNADA}]")


def _script_of(word: str) -> str:
    if _DEVANAGARI_RE.search(word):
        return "devanagari"
    if _KANNADA_RE.search(word):
        return "kannada"
    return "latin"


def _after_a_quantity(before: str) -> bool:
    """Does the captured name follow a number or a unit word?"""
    words = before.split()
    if not words:
        return False
    last = words[-1].lower()
    return last in _UNIT_LEAD_IN or any(ch.isdigit() for ch in last)


def _one_name(first: str, second: str, after_quantity: bool) -> bool:
    """Do these two words read as a single proper name ("ABC Suppliers")?

    They do not when the first word is the object of the sentence: in
    "5 kg chawal Anita ko" the customer is Anita and the rice is what was sold
    to her, so the first word has to be left where it is.

    This used to be decided by capitalisation, which Devanagari and Kannada do
    not have - so the test could never pass for them and every native two-word
    name was silently halved ("अनीता स्टोर्स" -> "स्टोर्स"). Position is the
    signal that works in all three scripts: the object follows the quantity.
    """
    if after_quantity:
        return False
    if first.lower() in _NOT_A_NAME:
        # A word this module itself produced ("sold", "kg") is never a name.
        return False
    # Same script, or not one name: one word rewritten into English and one not
    # means the rewritten one came from the vocabulary, so it is not a name.
    return _script_of(first) == _script_of(second)


def _move_postposition(text: str, pattern: re.Pattern[str], english: str) -> str:
    def swap(m: re.Match[str]) -> str:
        parts = m.group(1).split()
        kept: list[str] = []
        if len(parts) == 2 and not _one_name(
            parts[0], parts[1], _after_a_quantity(m.string[: m.start()])
        ):
            kept, parts = parts[:1], parts[1:]
        name = " ".join(parts)
        if not name or any(p.lower() in _NOT_A_NAME for p in parts):
            return m.group(0)
        if any(ch.isdigit() for ch in name):
            return m.group(0)
        return " ".join([*kept, english, name])

    return pattern.sub(swap, text)


# ---------------------------------------------------------------------------
# The one entry point
# ---------------------------------------------------------------------------
_FUTURE_HINTS = re.compile(r"(?:wants|चाहिए|चाहिये|ಬೇಕು|beku|order|ऑर्डर|ಆರ್ಡರ್)", re.IGNORECASE)
_KAL = re.compile(rf"(?<![\w{DEVANAGARI}])(?:कल|kal)(?![\w{DEVANAGARI}])", re.IGNORECASE)


def normalize(text: str) -> str:
    """Rewrite a note into the English shape the heuristic parser expects.

    Idempotent for text that is already English, so it is safe to run on
    everything rather than guessing the language first.
    """
    out = normalize_digits(text)
    out = out.replace("₹", " rs ")

    # Vocabulary first. Kannada is agglutinative, so an ordinary word can end in
    # the same syllable as a postposition — ಬಾಡಿಗೆ ("rent") ends in ಗೆ ("to").
    # Rewriting known words before hunting for postpositions stops "rent" being
    # split into "to ಬಾಡಿ".
    for pattern, english in _VOCAB_RE:
        out = pattern.sub(english, out)

    # Kannada's attached postpositions, then the separated forms.
    out = _KANNADA_SUFFIX_TO.sub(r"to \1", out)
    out = _KANNADA_SUFFIX_FROM.sub(r"from \1", out)
    out = _move_postposition(out, _TO_RE, "to")
    out = _move_postposition(out, _FROM_RE, "from")

    # कल means yesterday or tomorrow depending on tense. A shopkeeper logging
    # what happened means yesterday; one recording what a customer asked for
    # means tomorrow.
    if _KAL.search(out):
        out = _KAL.sub("tomorrow" if _FUTURE_HINTS.search(out) else "yesterday", out)

    return re.sub(r"\s+", " ", out).strip()
