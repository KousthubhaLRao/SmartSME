"""Turning tallies into something a person, or a paper, can read."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .runner import RunResult

RESULTS = Path(__file__).parent / "results"


def _pct(value: float) -> str:
    return f"{value * 100:5.1f}"


def table(results: list[RunResult], title: str) -> str:
    """One row per engine, one column group per field."""
    fields: list[str] = []
    for run in results:
        for name in run.report.fields:
            if name not in fields:
                fields.append(name)

    header = (
        f"### {title}\n\n| Engine | n | Exact | "
        + " | ".join(f"{f} P/R/F1" for f in fields)
        + " |\n"
    )
    header += "|---|---:|---:|" + "|".join(["---:"] * len(fields)) + "|\n"

    body = ""
    for run in results:
        cells = []
        for name in fields:
            score = run.report.fields.get(name)
            cells.append(
                f"{_pct(score.precision)}/{_pct(score.recall)}/{_pct(score.f1)}" if score else "-"
            )
        body += (
            f"| **{run.engine}** | {run.report.total} | "
            f"{_pct(run.report.exact_rate)}% | " + " | ".join(cells) + " |\n"
        )

    notes = ""
    for run in results:
        if run.report.fell_back:
            notes += (
                f"\n> **{run.engine}: {run.report.fell_back} of {run.report.total} examples "
                f"were produced by a different engine** (provider unavailable, so the pipeline "
                f"degraded as designed). Those rows are not a measurement of {run.engine}.\n"
            )
        if run.report.failures:
            shown = "; ".join(run.report.failures[:3])
            notes += f"\n> {run.engine}: {len(run.report.failures)} failed - {shown}\n"
    return header + body + notes


def per_language(run: RunResult, examples, title: str) -> str:
    """Where a single engine is strong and weak across the five variants."""
    by_lang: dict[str, list[bool]] = {}
    gold = {e.id: e for e in examples}
    for prediction in run.predictions:
        example = gold.get(prediction.example_id)
        if example is None or prediction.draft is None:
            continue
        from .metrics import Report

        one = Report()
        from .runner import score_note

        ok = score_note(one, prediction.draft, example.gold)
        by_lang.setdefault(example.lang, []).append(ok)

    out = f"### {title}\n\n| Variant | n | Exact |\n|---|---:|---:|\n"
    for lang, hits in sorted(by_lang.items()):
        out += f"| {lang} | {len(hits)} | {_pct(sum(hits) / len(hits))}% |\n"
    return out


def save(results: dict, name: str = "latest") -> Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    return path


def as_records(run: RunResult) -> list[dict]:
    """Every prediction, so a disagreement can be looked at rather than argued
    about. This is the file you read when a number looks wrong."""
    rows = []
    for p in run.predictions:
        row = {"id": p.example_id, "engine_used": p.engine_used, "seconds": round(p.seconds, 2)}
        if not p.ok:
            row["error"] = p.error
        elif p.draft is not None:
            row["party"] = p.draft.get("partyName")
            row["type"] = p.draft.get("suggestedType")
            for optional in ("amount", "category", "date"):
                if p.draft.get(optional) not in (None, "", 0):
                    row[optional] = p.draft.get(optional)
            row["items"] = [
                {"product": i.get("description"), "quantity": i.get("quantity")}
                for i in p.draft.get("items") or []
            ]
        elif p.invoice is not None:
            row["party"] = p.invoice.party
            row["phone"] = p.invoice.phone
            row["items"] = [
                {"product": li.product, "quantity": li.quantity} for li in p.invoice.lineItems
            ]
        rows.append(row)
    return rows


def header(engines: list[str]) -> str:
    return (
        f"# SmartSME extraction accuracy\n\n"
        f"Generated {datetime.now():%Y-%m-%d %H:%M} - engines: {', '.join(engines)}\n\n"
        "P/R/F1 are percentages. **Exact** is the share of inputs where every "
        "scored field was right, which is the share a shopkeeper could accept "
        "without editing anything.\n"
    )
