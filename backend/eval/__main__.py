"""Run the accuracy evaluation.

    python -m eval                              # every engine that has a key
    python -m eval --engines heuristic,google   # pick them
    python -m eval --slips-only --engines vision,ocrspace
    python -m eval --limit 10                   # a quick smoke run

Writes a markdown report to eval/results/ alongside a JSON file holding every
individual prediction, which is what you read when a number looks wrong.

This is deliberately NOT part of `pytest`. It makes real network calls, it is
nondeterministic, and a free tier is rate-limited - none of which belongs in a
suite that has to run in ten seconds on every change.
"""

from __future__ import annotations

import argparse
import sys

from app.ai import ocr_space
from app.core.config import settings

from . import report as reporting
from .dataset import LANGUAGES, load_catalogue, load_notes, load_slips
from .runner import IMAGE_ENGINES, TEXT_ENGINES, run_notes, run_slips


def available_text_engines() -> list[str]:
    """Heuristic always; a provider only when its key is present."""
    engines = ["heuristic"]
    for name, key in (
        ("anthropic", settings.anthropic_api_key),
        ("openai", settings.openai_api_key),
        ("google", settings.google_api_key),
    ):
        if key:
            engines.append(name)
    return engines


def available_image_engines() -> list[str]:
    engines = []
    if any((settings.anthropic_api_key, settings.openai_api_key, settings.google_api_key)):
        engines.append("vision")
    if ocr_space.enabled():
        engines.append("ocrspace")
    return engines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval", description=__doc__)
    parser.add_argument("--engines", default="", help="Comma-separated; default is all configured.")
    parser.add_argument("--limit", type=int, default=0, help="Only the first N examples.")
    parser.add_argument("--notes-only", action="store_true")
    parser.add_argument("--slips-only", action="store_true")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between calls. Free tiers are rate-limited; raise it on 429s.",
    )
    parser.add_argument("--name", default="latest", help="Output file name.")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    chosen = [e.strip() for e in args.engines.split(",") if e.strip()]
    catalogue = load_catalogue()
    notes = load_notes()
    slips = load_slips()
    if args.limit:
        notes, slips = notes[: args.limit], slips[: args.limit]

    sections: list[str] = []
    records: dict[str, list] = {}
    used: list[str] = []

    if not args.slips_only and notes:
        engines = [e for e in (chosen or available_text_engines()) if e in TEXT_ENGINES]
        runs = []
        for engine in engines:
            print(f"  notes x {engine} ({len(notes)} examples)...", flush=True)
            run = run_notes(notes, catalogue, engine, delay=args.delay)
            runs.append(run)
            records[f"notes.{engine}"] = reporting.as_records(run)
        if runs:
            used += engines
            sections.append(reporting.table(runs, f"Typed notes (n={len(notes)}, synthetic)"))
            for run in runs:
                sections.append(reporting.per_language(run, notes, f"By variant - {run.engine}"))

    if not args.notes_only and slips:
        engines = [e for e in (chosen or available_image_engines()) if e in IMAGE_ENGINES]
        runs = []
        for engine in engines:
            print(f"  slips x {engine} ({len(slips)} images)...", flush=True)
            run = run_slips(slips, engine, delay=args.delay)
            runs.append(run)
            records[f"slips.{engine}"] = reporting.as_records(run)
        if runs:
            used += engines
            sections.append(
                reporting.table(runs, f"Handwritten order slips (n={len(slips)}, real photographs)")
            )

    if not sections:
        print("Nothing to run. Configure a key, or check eval/data/.", file=sys.stderr)
        return 1

    languages = "\n".join(f"- `{k}` - {v}" for k, v in LANGUAGES.items())
    body = (
        reporting.header(used) + "\n" + "\n\n".join(sections) + f"\n\n### Variants\n\n{languages}\n"
    )

    reporting.RESULTS.mkdir(exist_ok=True)
    out = reporting.RESULTS / f"{args.name}.md"
    out.write_text(body, encoding="utf-8")
    reporting.save(records, args.name)

    print("\n" + body)
    print(f"\nwritten: {out}  and  {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
