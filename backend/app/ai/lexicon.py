"""What the goods are called, in the languages people actually order in.

`translit.py` can tell that अनीता is Anita. It cannot tell that चावल is rice -
that is not a spelling difference, it is a different word, and the only way to
know is to have been told.

So this is the telling: a retail vocabulary, mapped to one English concept per
row. A note in any of the three scripts, and a catalogue in any of them, both
reduce to the same concept, and that is what matching compares.

    "10 bori chawal"        -> concept "rice" -+
                                               +-> both -> "Rice Bag 25kg"
    catalogue "Rice Bag 25kg" -> concept "rice" +

**Adding to it is the point.** A row is `"english": (variants...)`, variants in
any script and any spelling; `fold()` already absorbs spelling differences, so
one form per language is usually enough. A shop selling something not listed
here still works - the item just has to be picked from the dropdown once
instead of being recognised.

This is a dictionary, not a translator. Machine translation was the obvious
alternative and is the wrong tool: it needs either a network round trip per
note or a few hundred megabytes of model, it is *worse* at exactly the words
that matter here (brand names, local produce names, "bori"), and its output
would still have to be matched against the shop's own catalogue afterwards -
which is the step that actually does the work.
"""

from __future__ import annotations

from .translit import fold_phrase

#: english concept -> the ways people write it.
#: Devanagari, Kannada, and the romanisations that fold differently.
LEXICON: dict[str, tuple[str, ...]] = {
    # -- grains, flours, staples ------------------------------------------
    "rice": ("चावल", "ಅಕ್ಕಿ", "chawal", "chaval", "akki"),
    "wheat": ("गेहूं", "गेहूँ", "ಗೋಧಿ", "gehun", "gehu", "godhi"),
    "flour": ("आटा", "ಹಿಟ್ಟು", "atta", "aata", "hittu"),
    "maida": ("मैदा", "ಮೈದಾ", "maida"),
    "semolina": ("सूजी", "रवा", "ರವೆ", "sooji", "suji", "rava", "rave"),
    "gram flour": ("बेसन", "ಕಡಲೆಹಿಟ್ಟು", "besan", "kadalehittu"),
    "poha": ("पोहा", "ಅವಲಕ್ಕಿ", "poha", "avalakki"),
    "vermicelli": ("सेवई", "ಶಾವಿಗೆ", "sevai", "semiya", "shavige"),
    # -- lentils and pulses ------------------------------------------------
    "lentil": ("दाल", "ಬೇಳೆ", "dal", "daal", "bele"),
    "toor dal": ("तूर", "अरहर", "ತೊಗರಿ", "toor", "tur", "arhar", "togari"),
    "moong dal": ("मूंग", "ಹೆಸರುಬೇಳೆ", "moong", "mung", "hesaru"),
    "chana": ("चना", "ಕಡಲೆ", "chana", "channa", "kadale"),
    "urad dal": ("उड़द", "ಉದ್ದು", "urad", "udad", "uddu"),
    "rajma": ("राजमा", "ರಾಜ್ಮಾ", "rajma"),
    # -- sweeteners, dairy, fats -------------------------------------------
    "sugar": ("चीनी", "शक्कर", "ಸಕ್ಕರೆ", "cheeni", "chini", "shakkar", "sakkare"),
    "jaggery": ("गुड़", "गुड", "ಬೆಲ್ಲ", "gud", "gur", "bella"),
    "salt": ("नमक", "ಉಪ್ಪು", "namak", "uppu"),
    "oil": ("तेल", "ಎಣ್ಣೆ", "tel", "tail", "enne"),
    "ghee": ("घी", "ತುಪ್ಪ", "ghee", "ghi", "tuppa"),
    "butter": ("मक्खन", "ಬೆಣ್ಣೆ", "makhan", "benne"),
    "milk": ("दूध", "ಹಾಲು", "doodh", "dudh", "haalu"),
    "curd": ("दही", "ಮೊಸರು", "dahi", "mosaru"),
    "paneer": ("पनीर", "ಪನೀರ್", "paneer"),
    "honey": ("शहद", "ಜೇನುತುಪ್ಪ", "shahad", "jenutuppa", "jenu"),
    # -- drinks -------------------------------------------------------------
    "tea": ("चाय", "चायपत्ती", "ಚಹಾ", "ಟೀ", "chai", "chaha", "chaay"),
    "coffee": ("कॉफ़ी", "कॉफी", "ಕಾಫಿ", "coffee", "kaapi", "kapi", "kafi"),
    "water": ("पानी", "ನೀರು", "pani", "paani", "neeru"),
    "soft drink": ("कोल्ड ड्रिंक", "ಕೋಲ್ಡ್ ಡ್ರಿಂಕ್", "cold drink", "thanda"),
    # -- spices -------------------------------------------------------------
    "turmeric": ("हल्दी", "ಅರಿಶಿನ", "haldi", "arishina"),
    "chilli": ("मिर्च", "मिर्ची", "ಮೆಣಸಿನಕಾಯಿ", "mirch", "mirchi", "menasinakayi"),
    "pepper": ("काली मिर्च", "ಕರಿಮೆಣಸು", "kali mirch", "karimenasu"),
    "coriander": ("धनिया", "ಕೊತ್ತಂಬರಿ", "dhaniya", "dhania", "kottambari"),
    "cumin": ("जीरा", "ಜೀರಿಗೆ", "jeera", "jira", "jeerige"),
    "mustard": ("सरसों", "ಸಾಸಿವೆ", "sarson", "sasive"),
    "fenugreek": ("मेथी", "ಮೆಂತ್ಯ", "methi", "mentya"),
    "asafoetida": ("हींग", "ಇಂಗು", "hing", "ingu"),
    "cardamom": ("इलायची", "ಏಲಕ್ಕಿ", "elaichi", "ilaichi", "yalakki"),
    "clove": ("लौंग", "ಲವಂಗ", "laung", "lavanga"),
    "cinnamon": ("दालचीनी", "ಚಕ್ಕೆ", "dalchini", "chakke"),
    "masala": ("मसाला", "ಮಸಾಲೆ", "masala", "masale"),
    "tamarind": ("इमली", "ಹುಣಸೆ", "imli", "hunase"),
    # -- produce -------------------------------------------------------------
    "onion": ("प्याज", "प्याज़", "ಈರುಳ್ಳಿ", "pyaz", "pyaj", "kanda", "eerulli"),
    "potato": ("आलू", "ಆಲೂಗಡ್ಡೆ", "aloo", "alu", "alugadde"),
    "tomato": ("टमाटर", "ಟೊಮೇಟೊ", "tamatar", "tomato"),
    "garlic": ("लहसुन", "ಬೆಳ್ಳುಳ್ಳಿ", "lehsun", "lahsun", "bellulli"),
    "ginger": ("अदरक", "ಶುಂಠಿ", "adrak", "shunti"),
    "brinjal": ("बैंगन", "ಬದನೆಕಾಯಿ", "baingan", "badanekayi"),
    "lemon": ("नींबू", "ನಿಂಬೆ", "nimbu", "neembu", "nimbe"),
    "banana": ("केला", "ಬಾಳೆಹಣ್ಣು", "kela", "balehannu"),
    "coconut": ("नारियल", "ತೆಂಗಿನಕಾಯಿ", "nariyal", "tenginakayi", "kobbari"),
    "peanut": ("मूंगफली", "ಕಡಲೆಕಾಯಿ", "mungfali", "moongphali", "kadalekayi"),
    "cashew": ("काजू", "ಗೋಡಂಬಿ", "kaju", "godambi"),
    "almond": ("बादाम", "ಬಾದಾಮಿ", "badam", "badami"),
    # -- packaged goods ------------------------------------------------------
    "biscuit": ("बिस्कुट", "बिस्किट", "ಬಿಸ್ಕತ್ತು", "biscuit", "biskut", "biskattu"),
    "bread": ("ब्रेड", "डबलरोटी", "ಬ್ರೆಡ್", "bread", "dabalroti"),
    "egg": ("अंडा", "अंडे", "ಮೊಟ್ಟೆ", "anda", "ande", "motte"),
    "noodles": ("नूडल्स", "ನೂಡಲ್ಸ್", "noodles", "maggi"),
    "chips": ("चिप्स", "ಚಿಪ್ಸ್", "chips"),
    "chocolate": ("चॉकलेट", "ಚಾಕಲೇಟ್", "chocolate"),
    "pickle": ("अचार", "ಉಪ್ಪಿನಕಾಯಿ", "achar", "achaar", "uppinakayi"),
    "papad": ("पापड़", "ಹಪ್ಪಳ", "papad", "happala"),
    # -- household -----------------------------------------------------------
    "soap": ("साबुन", "ಸಾಬೂನು", "sabun", "saboon", "sabunu"),
    "detergent": ("डिटर्जेंट", "सर्फ", "ಡಿಟರ್ಜೆಂಟ್", "detergent", "surf"),
    "shampoo": ("शैम्पू", "ಶಾಂಪೂ", "shampoo"),
    "toothpaste": ("टूथपेस्ट", "ಟೂತ್ ಪೇಸ್ಟ್", "toothpaste", "manjan"),
    "matchbox": ("माचिस", "ಬೆಂಕಿಪೊಟ್ಟಣ", "machis", "benkipottana"),
    "candle": ("मोमबत्ती", "ಮೇಣದಬತ್ತಿ", "mombatti", "menadabatti"),
    "incense": ("अगरबत्ती", "ಊದುಬತ್ತಿ", "agarbatti", "udubatti"),
    "broom": ("झाड़ू", "ಪೊರಕೆ", "jhadu", "porake"),
    "bucket": ("बाल्टी", "ಬಕೆಟ್", "balti", "baket"),
    "bulb": ("बल्ब", "ಬಲ್ಬ್", "bulb"),
    "battery": ("बैटरी", "ಬ್ಯಾಟರಿ", "battery", "cell"),
    # -- building and hardware -----------------------------------------------
    "cement": ("सीमेंट", "ಸಿಮೆಂಟ್", "cement"),
    "sand": ("रेत", "बालू", "ಮರಳು", "ret", "balu", "maralu"),
    "brick": ("ईंट", "ಇಟ್ಟಿಗೆ", "eent", "int", "ittige"),
    "tile": ("टाइल", "ಟೈಲ್ಸ್", "tile", "tiles"),
    "paint": ("पेंट", "रंग", "ಬಣ್ಣ", "paint", "rang", "banna"),
    "nail": ("कील", "ಮೊಳೆ", "keel", "kil", "mole"),
    "screw": ("पेंच", "ಸ್ಕ್ರೂ", "pench", "screw", "screws"),
    "wire": ("तार", "ಕೇಬಲ್", "taar", "wire", "cable"),
    "pipe": ("पाइप", "ಪೈಪ್", "pipe", "pvc pipe"),
    "tap": ("नल", "ಟ್ಯಾಪ್", "nal", "tap", "taps"),
    "wash basin": ("वॉश बेसिन", "ಬೇಸಿನ್", "wash basin", "basin"),
    "grinder": ("ग्राइंडर", "ಗ್ರೈಂಡರ್", "grinder"),
    "mixer": ("मिक्सर", "ಮಿಕ್ಸರ್", "mixer", "mixie"),
    "switch board": ("स्विच बोर्ड", "ಸ್ವಿಚ್ ಬೋರ್ಡ್", "switch board", "switchboard"),
    # -- furnishing and furniture --------------------------------------------
    "chair": ("कुर्सी", "ಕುರ್ಚಿ", "kursi", "kurchi"),
    "table": ("मेज", "ಮೇಜು", "mez", "meju"),
    "curtain": ("परदा", "ಪರದೆ", "parda", "parade", "curtains"),
    "rod": ("रॉड", "ಸರಳು", "rod", "saralu"),
    "bracket": ("ब्रैकेट", "ಬ್ರಾಕೆಟ್", "bracket", "brackets"),
    "cloth": ("कपड़ा", "ಬಟ್ಟೆ", "kapda", "batte"),
    # -- stationery ------------------------------------------------------------
    "pen": ("पेन", "ಪೆನ್ನು", "pen", "kalam"),
    "notebook": ("कॉपी", "नोटबुक", "ಪುಸ್ತಕ", "notebook", "pustaka"),
}


def _build_index() -> dict[str, str]:
    """Folded key -> concept, for every way of writing every entry.

    Built once at import. First writer wins on a clash, so an earlier row keeps
    a key a later row would have stolen, and the table stays readable top-down.
    """
    index: dict[str, str] = {}
    for concept, variants in LEXICON.items():
        for spelling in (concept, *variants):
            key = fold_phrase(spelling)
            if key:
                index.setdefault(key, concept)
                # A multi-word entry is also reachable by its last word, which
                # is the one carrying the meaning: "kali mirch" -> "mirch".
                last = key.split()[-1]
                index.setdefault(last, concept)
    return index


_INDEX = _build_index()


def concept_of(phrase: str | None) -> str | None:
    """The one concept this phrase names, or None if it names nothing known."""
    if not phrase:
        return None
    key = fold_phrase(phrase)
    if not key:
        return None
    if key in _INDEX:
        return _INDEX[key]
    for token in key.split():
        if token in _INDEX:
            return _INDEX[token]
    return None


def concepts_in(phrase: str | None) -> set[str]:
    """Every concept named anywhere in a phrase.

    A catalogue entry is a sentence more than a word - "Wheat Flour 10kg" names
    two - so a note saying आटा and a note saying गेहूं should both find it.
    """
    if not phrase:
        return set()
    key = fold_phrase(phrase)
    if not key:
        return set()
    found = {_INDEX[token] for token in key.split() if token in _INDEX}
    whole = _INDEX.get(key)
    if whole:
        found.add(whole)
    return found


def known_words() -> int:
    """How many spellings the lexicon recognises. For the /api/ai/status page."""
    return len(_INDEX)


__all__ = ["LEXICON", "concept_of", "concepts_in", "known_words"]
