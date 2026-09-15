"""Counting what the system got right.

Extraction is scored the way information extraction is normally scored, as a
retrieval problem per field rather than as a percentage correct:

* **true positive**  - there was an answer and we produced it
* **false positive** - we produced an answer that is wrong, or produced one
  where there was nothing to find
* **false negative** - there was an answer and we missed it or got it wrong

A wrong answer therefore costs twice: once as a miss, once as a fabrication.
That is deliberate. In this product a wrong customer is worse than no customer,
because no customer leaves an empty dropdown and a wrong one silently bills
somebody who never ordered.

Accuracy alone would hide that. A parser that answers "Anita Stores" to
everything would look good on a dataset where Anita is common, and precision is
what catches it.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field


def norm(value: object) -> str:
    """Compare on meaning, not typography: case, spacing, punctuation and
    Unicode form are not what is being measured."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _number(value: object) -> float | None:
    """The numeric value, if this is a number at all."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def same(predicted: object, gold: object) -> bool:
    """Is this the same answer?

    Numbers are compared as numbers. The amount 300 and the amount 300.0 are
    one answer, and comparing them as text scored a correct extraction wrong -
    which is the kind of bug that makes an evaluation worse than none, because
    it reports a real success as a failure and someone goes looking for it in
    the parser.
    """
    p, g = _number(predicted), _number(gold)
    if p is not None and g is not None:
        return abs(p - g) < 0.005
    return norm(predicted) == norm(gold)


@dataclass
class Score:
    """Tallies for one field across a whole dataset."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def support(self) -> int:
        """How many answers the gold labels actually contain."""
        return self.tp + self.fn

    def add_scalar(self, predicted: object, gold: object) -> bool:
        """One single-valued field. Returns True when it was exactly right."""
        p, g = norm(predicted), norm(gold)
        if g and same(predicted, gold):
            self.tp += 1
            return True
        if g and not p:
            self.fn += 1  # missed it
        elif g:
            self.fn += 1  # got it wrong: a miss and a fabrication
            self.fp += 1
        elif p:
            self.fp += 1  # invented an answer where there was none
        else:
            return True  # nothing to find, nothing found
        return False

    def add_set(self, predicted: list, gold: list) -> bool:
        """A repeated field - the line items. Compared as a multiset, so two
        kilos of coffee is not the same answer as one."""
        p, g = Counter(predicted), Counter(gold)
        hits = sum((p & g).values())
        self.tp += hits
        self.fp += sum(p.values()) - hits
        self.fn += sum(g.values()) - hits
        return p == g


@dataclass
class Report:
    """Every field, plus the number that actually matters to a user."""

    fields: dict[str, Score] = field(default_factory=dict)
    exact: int = 0
    total: int = 0
    #: Examples where the engine silently fell back to another one.
    fell_back: int = 0
    failures: list[str] = field(default_factory=list)

    def score(self, name: str) -> Score:
        return self.fields.setdefault(name, Score())

    @property
    def exact_rate(self) -> float:
        """Share of inputs a shopkeeper could accept without editing anything.

        The headline number. Field-level F1 can look healthy while almost every
        draft still needs a correction somewhere, and it is the whole draft a
        person has to approve.
        """
        return self.exact / self.total if self.total else 0.0
