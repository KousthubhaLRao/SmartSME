"""The labelled data, and the shop it is scored against.

A **gold label** is the answer a careful human gives for one input, written
down before any system sees it. "sold 5 kg rice to Anita Stores" has the gold
label `{type: sale, party: Anita Stores, items: [Rice Bag 25kg x5]}`. Scoring
is then just comparing what came out against that, and every number in the
report is a count of agreements and disagreements.

Gold labels are the part that cannot be automated, because they are the
definition of correct. Anything a model produced is a prediction, not a label -
grading a model against its own output measures nothing.

Two sets live here, and they are **not** of equal standing:

* `slips.jsonl` - twelve real photographs of handwritten orders. Real inputs;
  the labels are a transcription of what is on the paper.
* `notes.jsonl` - typed notes written by the author to cover the grammar of the
  five language variants. **Synthetic.** Useful for catching regressions and
  comparing engines against each other on identical input; not evidence of how
  the system behaves on real shopkeepers, because nobody in the sample is one.

Anything published from this needs the second set replaced by notes collected
from actual users, ideally labelled twice by different people so the agreement
between them can be reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data"

#: Language variants, as they appear in the data.
LANGUAGES = {
    "en": "English",
    "hi-latn": "Hindi in Latin letters",
    "hi": "Hindi (Devanagari)",
    "kn-latn": "Kannada in Latin letters",
    "kn": "Kannada (Kannada script)",
}


@dataclass
class Row:
    """A catalogue entry, shaped like the ORM object the matcher expects.

    The evaluation deliberately does not read the development database: a
    number is only comparable to another number if both were produced against
    the same shop.
    """

    id: str
    name: str
    type: str = "customer"
    phone: str | None = None
    selling_price: float = 0.0
    purchase_price: float = 0.0
    stock: float = 0.0


@dataclass
class Catalogue:
    parties: list[Row] = field(default_factory=list)
    products: list[Row] = field(default_factory=list)


@dataclass
class Example:
    id: str
    gold: dict[str, Any]
    #: Text examples carry `text`; slip examples carry `image`.
    text: str | None = None
    image: str | None = None
    lang: str = "en"
    note: str = ""


def load_catalogue() -> Catalogue:
    raw = json.loads((DATA / "catalogue.json").read_text(encoding="utf-8"))
    return Catalogue(
        parties=[
            Row(
                id=p["id"],
                name=p["name"],
                type=p.get("type", "customer"),
                phone=p.get("phone"),
            )
            for p in raw["parties"]
        ],
        products=[
            Row(
                id=p["id"],
                name=p["name"],
                selling_price=p.get("sellingPrice", 0),
                purchase_price=p.get("purchasePrice", 0),
                stock=p.get("stock", 0),
            )
            for p in raw["products"]
        ],
    )


def _load(filename: str) -> list[Example]:
    path = DATA / filename
    if not path.exists():
        return []
    out: list[Example] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as err:
            raise ValueError(f"{filename}:{line_no}: {err}") from err
        if "gold" not in record:
            raise ValueError(f"{filename}:{line_no}: every example needs a gold label")
        out.append(
            Example(
                id=record.get("id") or f"{filename}:{line_no}",
                gold=record["gold"],
                text=record.get("text"),
                image=record.get("image"),
                lang=record.get("lang", "en"),
                note=record.get("note", ""),
            )
        )
    return out


def load_notes() -> list[Example]:
    return _load("notes.jsonl")


def load_slips() -> list[Example]:
    return _load("slips.jsonl")


def image_path(example: Example) -> Path:
    """Slip images live with the tests; there is no reason to keep two copies."""
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / (example.image or "")
