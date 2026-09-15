"""Running the labelled data through a chosen engine, and scoring the result.

The evaluation calls the same functions the application calls - `parse_command`
then `ground_text` for a note, `read_image` for a photograph. Nothing is
reimplemented here, because a harness that reimplements the pipeline measures
the harness.

Two hazards get explicit handling, both of which would otherwise produce a
number that looks fine and means nothing:

**Silent fallback.** Every AI path in this codebase degrades to the heuristic
parser rather than failing, which is right for a shopkeeper and wrong for a
measurement: a run labelled "gemini" whose provider was rate-limited would
quietly report the regex parser's score under Gemini's name. So the engine that
actually produced each draft is recorded, and any disagreement is counted and
printed.

**The circuit breaker.** Three consecutive provider failures disable it for two
minutes. In the app that is a feature; mid-evaluation it would convert one blip
into dozens of heuristic results. It is reset before each call.
"""

from __future__ import annotations

import base64
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.ai import client as ai_client
from app.ai.nlp import parse_command
from app.ai.ocr import ParsedInvoice
from app.core.config import settings
from app.smart_input import ground_text, read_image

from .dataset import Catalogue, Example, image_path
from .metrics import Report, norm

#: Keys the engine chooser has to be able to switch off.
_KEYS = ("anthropic_api_key", "openai_api_key", "google_api_key")

#: Engines that run locally. Pacing them wastes minutes and protects nothing.
OFFLINE = {"heuristic"}


def pace(engine: str, delay: float) -> None:
    """Stay inside a free tier's per-minute allowance.

    Measured rather than guessed: at one second between calls, Gemini's free
    tier served sixteen requests and then refused everything until the minute
    rolled over - and because every AI path here degrades to the heuristic
    parser rather than failing, those refusals came back as *results*. Half a
    run was silently the regex parser wearing Gemini's name.
    """
    if delay and engine not in OFFLINE:
        time.sleep(delay)

TEXT_ENGINES = ("heuristic", "anthropic", "openai", "google")
IMAGE_ENGINES = ("vision", "ocrspace")


@contextmanager
def engine_context(name: str):
    """Force one engine for the duration, then put the settings back."""
    saved = {k: getattr(settings, k) for k in (*_KEYS, "ai_provider", "ocr_space_api_key")}
    try:
        if name in ("heuristic", "ocrspace"):
            # No provider at all: the heuristic parser and, for images, the
            # OCR.space fallback are what remain.
            for key in _KEYS:
                setattr(settings, key, "")
            settings.ai_provider = ""
        elif name == "vision":
            settings.ocr_space_api_key = ""  # so a fallback cannot be mistaken for the model
        else:
            settings.ai_provider = name
        yield
    finally:
        for key, value in saved.items():
            setattr(settings, key, value)


#: `read_image` reports which path it took, and those names are not the flags
#: used to select them. Getting this mapping wrong made the fallback check cry
#: wolf on every single image - a false alarm in the one check whose job is to
#: stop a contaminated run being read as a real measurement.
IMAGE_PATH = {"vision": "vision", "ocrspace": "ocr.space"}


def expected_label(name: str) -> str:
    """What `draft["engine"]` should say if the intended engine really ran."""
    if name in ("heuristic", "ocrspace"):
        return "Heuristic" if name == "heuristic" else "ocr.space"
    provider = ai_client.get_provider(vision=(name == "vision"))
    return provider.label if provider else "Heuristic"


@dataclass
class Prediction:
    example_id: str
    engine_used: str
    ok: bool = True
    error: str = ""
    draft: dict[str, Any] | None = None
    invoice: ParsedInvoice | None = None
    seconds: float = 0.0


@dataclass
class RunResult:
    engine: str
    predictions: list[Prediction] = field(default_factory=list)
    report: Report = field(default_factory=Report)


def _attempt(call, retries: int, delay: float):
    """Retry transient provider trouble; a free tier is a busy tier."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        ai_client.reset_breaker()
        try:
            return call()
        except Exception as err:
            last = err
            if attempt < retries:
                time.sleep(delay * (attempt + 1))
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
def _gold_items(gold: dict) -> list[tuple[str, int]]:
    return [(norm(i.get("product")), int(i.get("quantity", 1))) for i in gold.get("items") or []]


def _drafted_items(draft: dict) -> list[tuple[str, int]]:
    return [
        (norm(i.get("description")), int(i.get("quantity", 1))) for i in draft.get("items") or []
    ]


def score_note(report: Report, draft: dict, gold: dict) -> bool:
    """Compare one draft against its gold label. True when nothing needs editing."""
    perfect = True
    perfect &= report.score("type").add_scalar(draft.get("suggestedType"), gold.get("type"))
    perfect &= report.score("party").add_scalar(draft.get("partyName"), gold.get("party"))
    perfect &= report.score("items").add_set(_drafted_items(draft), _gold_items(gold))
    # Optional fields are only scored where the label says something about them,
    # except that inventing one still counts against precision.
    for name, predicted, expected in (
        ("amount", draft.get("amount"), gold.get("amount")),
        ("category", draft.get("category"), gold.get("category")),
        ("date", draft.get("date"), gold.get("date")),
    ):
        if expected is None and predicted in (None, "", 0, "General"):
            continue
        perfect &= report.score(name).add_scalar(predicted, expected)
    return perfect


def run_notes(
    examples: list[Example],
    catalogue: Catalogue,
    engine: str,
    *,
    delay: float = 0.0,
    retries: int = 2,
) -> RunResult:
    result = RunResult(engine=engine)
    with engine_context(engine):
        wanted = expected_label(engine)
        for example in examples:
            started = time.monotonic()
            try:
                parsed = _attempt(lambda e=example: parse_command(e.text or ""), retries, 2.0)
                draft = ground_text(
                    parsed, catalogue.parties, catalogue.products, note=example.text or ""
                )
            except Exception as err:
                result.predictions.append(
                    Prediction(example.id, engine, ok=False, error=f"{type(err).__name__}: {err}")
                )
                result.report.total += 1
                result.report.failures.append(f"{example.id}: {err}")
                continue

            used = draft.get("engine", "?")
            if norm(used) != norm(wanted):
                result.report.fell_back += 1
            result.report.total += 1
            if score_note(result.report, draft, example.gold):
                result.report.exact += 1
            result.predictions.append(
                Prediction(example.id, used, draft=draft, seconds=time.monotonic() - started)
            )
            pace(engine, delay)
    return result


# ---------------------------------------------------------------------------
# Slips
# ---------------------------------------------------------------------------
def score_slip(report: Report, invoice: ParsedInvoice, gold: dict) -> bool:
    perfect = True
    perfect &= report.score("party").add_scalar(invoice.party, gold.get("party"))
    perfect &= report.score("phone").add_scalar(invoice.phone, gold.get("phone"))
    predicted = [(norm(li.product), int(li.quantity)) for li in invoice.lineItems]
    perfect &= report.score("items").add_set(predicted, _gold_items(gold))
    return perfect


def run_slips(
    examples: list[Example],
    engine: str,
    *,
    delay: float = 0.0,
    retries: int = 2,
) -> RunResult:
    result = RunResult(engine=engine)
    with engine_context(engine):
        for example in examples:
            path = image_path(example)
            started = time.monotonic()
            if not path.exists():
                result.report.failures.append(f"{example.id}: no image at {path}")
                result.report.total += 1
                continue
            encoded = base64.b64encode(path.read_bytes()).decode()
            try:
                invoice, used = _attempt(
                    lambda d=encoded: read_image(d, "image/jpeg"), retries, 3.0
                )
            except Exception as err:
                result.predictions.append(
                    Prediction(example.id, engine, ok=False, error=f"{type(err).__name__}: {err}")
                )
                result.report.total += 1
                result.report.failures.append(f"{example.id}: {err}")
                continue

            if used != IMAGE_PATH[engine]:
                result.report.fell_back += 1
            result.report.total += 1
            if score_slip(result.report, invoice, example.gold):
                result.report.exact += 1
            result.predictions.append(
                Prediction(example.id, used, invoice=invoice, seconds=time.monotonic() - started)
            )
            pace(engine, delay)
    return result
