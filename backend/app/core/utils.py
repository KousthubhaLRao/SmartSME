"""Small shared helpers, ported from the previous `lib/utils.ts`."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def round2(n: float) -> float:
    """Round half-up to 2 decimals, matching the previous JS behaviour."""
    if n is None:
        return 0.0
    # Adding a tiny epsilon mirrors the JS `Math.round((n + EPSILON) * 100) / 100`
    # so values like 1.005 round up rather than down.
    return int(n * 100 + (0.5 if n >= 0 else -0.5) + (1e-9 if n >= 0 else -1e-9)) / 100


def group_number(amount: float, decimals: int = 2) -> str:
    """Indian-style digit grouping, e.g. 1,23,456.00.

    `decimals=0` drops the paise, which is what the dashboard tiles use.
    """
    neg = amount < 0
    whole, frac = divmod(round(abs(amount) * 100), 100) if decimals else (round(abs(amount)), 0)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join([*parts, tail])
    out = f"{s}.{frac:02d}" if decimals else s
    return f"-{out}" if neg else out


def money(amount: float, currency: str = "INR", decimals: int = 2) -> str:
    """Format an amount with its currency symbol."""
    return f"{CURRENCY_SYMBOLS.get(currency, '')}{group_number(amount or 0, decimals)}"


def format_date(d: datetime | str) -> str:
    dt = d if isinstance(d, datetime) else datetime.fromisoformat(str(d))
    return dt.strftime("%d %b %Y")


def parse_date_input(value: object) -> datetime | None:
    """Parse a `yyyy-mm-dd` (or ISO) value; None when blank or unparseable.

    A bare `yyyy-mm-dd` is anchored to local noon so it can never land on the
    previous calendar day once stored.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if _ISO_DATE.match(raw):
            return datetime.fromisoformat(raw).replace(hour=12)
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def to_date_input_value(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def start_of_day(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def end_of_day(d: datetime) -> datetime:
    return d.replace(hour=23, minute=59, second=59, microsecond=999000)


def shift_days(d: datetime, days: int) -> datetime:
    return start_of_day(d) + timedelta(days=days)


def initials(name: str) -> str:
    return "".join(p[0].upper() for p in name.split()[:2] if p)
