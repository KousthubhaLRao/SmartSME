"""One comparable form for three scripts.

A shopkeeper types "chawal", "चावल" or "ಅಕ್ಕಿ"; their catalogue says
"Rice Bag 25kg". Nothing matches, because string comparison has no idea these
are the same thing. Two different problems are tangled together there, and they
need different answers:

* **Products can be translated.** चावल *means* rice. That is `lexicon.py`.
* **Names can only be transliterated.** There is no dictionary entry for
  अनीता - it is Anita, written in another alphabet. That is this module.

On top of both sits a third problem: romanised Indian words have no fixed
spelling. chawal, chaval and chaawal are one word typed by three people, and
अनीता transliterates to "anītā" while the party list says "Anita". So every
comparison here happens on a *folded* key that throws away the ways people
differ and keeps what they agree on.

Nothing here is a model. `indic_transliteration` is a character-mapping library
(pure Python, no downloads, 0.2s to import), the folding is a dozen rules, and
all of it runs offline in microseconds.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

#: The two Indic scripts SmartSME reads, by Unicode block.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_KANNADA = re.compile(r"[ಀ-೿]")

_SCHEMES = {
    "devanagari": sanscript.DEVANAGARI,
    "kannada": sanscript.KANNADA,
}


def script_of(text: str) -> str:
    """Which alphabet this is written in: devanagari, kannada or latin."""
    if _DEVANAGARI.search(text):
        return "devanagari"
    if _KANNADA.search(text):
        return "kannada"
    return "latin"


@lru_cache(maxsize=4096)
def to_latin(text: str) -> str:
    """Rewrite Devanagari or Kannada in Latin letters. Latin passes through.

    IAST is the target because it is lossless and reversible - it keeps the
    long/short vowel and retroflex distinctions as diacritics, which `fold()`
    then drops deliberately rather than by accident.
    """
    scheme = _SCHEMES.get(script_of(text))
    if scheme is None:
        return text
    return transliterate(text, scheme, sanscript.IAST)


def _strip_marks(text: str) -> str:
    """ā -> a, ṭ -> t, ś -> s: the diacritics IAST uses, removed."""
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))


#: Digraphs that different romanisation conventions disagree about, applied in
#: this order.
#:
#: The aspirates are the ones that matter for names. Indic scripts distinguish
#: त from थ, but the people writing those names in English do not: Anita and
#: Anitha, Geeta and Geetha, Sunita and Sunitha are each one person choosing
#: between two spellings of their own name. Folding them together is why a
#: party list is searchable at all.
#:
#: Then the long vowels, for the same reason on the other axis: nobody agrees
#: whether ई is "ee" or "i".
_DIGRAPHS = (
    ("chh", "c"),
    ("ch", "c"),
    ("sh", "s"),
    ("th", "t"),
    ("dh", "d"),
    ("kh", "k"),
    ("gh", "g"),
    ("bh", "b"),
    ("jh", "j"),
    ("ph", "f"),
    ("aa", "a"),
    ("ee", "i"),
    ("oo", "u"),
    ("ii", "i"),
)

#: Single letters people swap freely writing Indian words in English.
_EQUIVALENT = str.maketrans({"w": "v", "z": "j", "q": "k", "y": "i"})

_DOUBLED = re.compile(r"(.)\1+")
_NON_KEY = re.compile(r"[^a-z0-9]+")


@lru_cache(maxsize=8192)
def fold(word: str) -> str:
    """A spelling-insensitive key for one word.

    Everything that varies between writers of the same word is removed, so the
    comparison is on what they agree about:

        chawal, chaval, chaawal, चावल   ->  caval
        akki, ಅಕ್ಕಿ                       ->  aki
        Anita, Anitha, अनीता, ಅನಿತಾ     ->  anit

    The trailing vowel goes because Devanagari carries an inherent "a" that
    transliterates into every word ("cāvala") and that nobody types in English.
    """
    w = _strip_marks(to_latin(word)).lower()
    for old, new in _DIGRAPHS:
        w = w.replace(old, new)
    w = w.translate(_EQUIVALENT)
    w = _NON_KEY.sub("", w)
    w = _DOUBLED.sub(r"\1", w)
    if len(w) > 3 and w.endswith("a"):
        w = w[:-1]
    return w


def stem(token: str) -> str:
    """Crude, deliberately: a catalogue says "Biscuits" and a note says
    "biscuit", and that is the only difference worth papering over here."""
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def fold_phrase(phrase: str) -> str:
    """Fold every word, and reduce plurals, so one written form covers both.

    The stemming is what stops a vocabulary from needing "nail" and "nails" and
    "tile" and "tiles" listed by hand, which is a list nobody finishes.
    """
    return " ".join(k for k in (stem(fold(w)) for w in phrase.split()) if k)


_VOWELS = re.compile(r"[aeiou]")


@lru_cache(maxsize=8192)
def skeleton(word: str) -> str:
    """The consonants of a folded word, in order.

    A last resort, and treated like one. Transliteration cannot recover a vowel
    the original script never wrote: स्टोर्स comes out "storsa" where the shop
    wrote "Stores", and no amount of folding closes that gap - but "strs" and
    "strs" are the same. It is also lossy enough to collide, so callers only
    trust it when exactly one candidate matches.
    """
    return _VOWELS.sub("", fold(word))


__all__ = ["fold", "fold_phrase", "script_of", "skeleton", "to_latin"]
