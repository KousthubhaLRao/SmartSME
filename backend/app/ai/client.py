"""The AI layer: one provider, one call.

Google Gemini, because its free tier needs no card and the same key reads both
a typed note and a photographed order slip. Set `GOOGLE_API_KEY` and it is used;
leave it unset and everything still works - text falls back to the built-in
regex parser and photographs to OCR.space.

This used to be provider-agnostic, with Anthropic, OpenAI-compatible endpoints
and Groq alongside Gemini. That flexibility was never used and cost real money
to carry: four sets of settings in `.env`, four code paths, four sets of pinned
model names to go stale - two of which were silently returning 404 before anyone
checked. One provider that is actually configured is worth more than four that
are not.

Swapping providers later is a contained change: one `complete()` implementation
and the settings behind it.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass

import httpx

from ..core.config import settings

log = logging.getLogger("smartsme.ai")

TIMEOUT = httpx.Timeout(60.0, connect=10.0)

#: A provider that is down is not worth waiting a minute for, over and over.
#: Nothing that calls it is urgent enough to justify that: every caller has a
#: heuristic fallback, and the alternative is a queue of twenty-five mailed
#: orders taking twenty-five minutes to fail one at a time.
#:
#: So after this many consecutive failures the provider is skipped outright for
#: a cooling-off period, and callers degrade to the heuristic immediately.
_BREAKER_FAILURES = 3
_BREAKER_COOLDOWN = 120.0

_breaker_lock = threading.Lock()
_consecutive_failures = 0
_skip_until = 0.0


class ProviderUnavailable(RuntimeError):
    """Raised instead of calling a provider that has just been failing."""


def _breaker_is_open() -> bool:
    with _breaker_lock:
        return time.monotonic() < _skip_until


def _record_success() -> None:
    global _consecutive_failures, _skip_until
    with _breaker_lock:
        _consecutive_failures = 0
        _skip_until = 0.0


def _record_failure() -> None:
    global _consecutive_failures, _skip_until
    with _breaker_lock:
        _consecutive_failures += 1
        tripped = _consecutive_failures if _consecutive_failures >= _BREAKER_FAILURES else 0
        if tripped:
            _skip_until = time.monotonic() + _BREAKER_COOLDOWN
    if tripped:
        log.warning(
            "AI provider failed %s times in a row; using the heuristic parser for %ss",
            tripped,
            int(_BREAKER_COOLDOWN),
        )


def reset_breaker() -> None:
    """Forget the recent failures. For tests, and for a changed configuration."""
    _record_success()


@dataclass(slots=True)
class AiImage:
    base64: str
    media_type: str


@dataclass(slots=True)
class AiProvider:
    id: str
    label: str
    model: str
    vision: bool
    api_key: str

    def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        image: AiImage | None = None,
        max_tokens: int = 1024,
    ) -> str:
        if _breaker_is_open():
            raise ProviderUnavailable(f"{self.label} is failing; skipping it for now")
        try:
            out = _gemini_complete(self, prompt, system, image, max_tokens)
        except Exception:
            _record_failure()
            raise
        _record_success()
        return out


def _gemini_complete(
    p: AiProvider, prompt: str, system: str | None, image: AiImage | None, max_tokens: int
) -> str:
    parts: list[dict] = [{"text": f"{system}\n\n{prompt}" if system else prompt}]
    if image:
        parts.append({"inlineData": {"mimeType": image.media_type, "data": image.base64}})

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{p.model}:generateContent"
        f"?key={p.api_key}"
    )
    with httpx.Client(timeout=TIMEOUT) as client:
        res = client.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "responseMimeType": "application/json",
                    # Zero, because this is extraction and not writing. Left at
                    # the default, the same note produced different drafts on
                    # repeated runs: measured on five notes over three runs,
                    # two came back different - once the customer's name kept
                    # its Kannada case-ending and stopped matching, once the
                    # line items vanished entirely and became "Item x1".
                    # Somebody typing the same order twice must not get two
                    # different sales.
                    "temperature": 0,
                },
            },
        )
    if res.status_code >= 400:
        raise RuntimeError(f"AI request failed ({res.status_code}). {res.text[:200]}")
    data = res.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    return "".join(
        part.get("text", "") for part in candidates[0].get("content", {}).get("parts", [])
    )


def get_provider(*, vision: bool = False) -> AiProvider | None:
    """The configured provider, or None when there is no key.

    `vision` is kept in the signature even though Gemini reads images either
    way: callers say what they need, and the day a text-only model is configured
    the check is already in the right place rather than needing to be found.
    """
    if not settings.google_api_key:
        return None
    provider = AiProvider(
        id="google",
        label="Google Gemini",
        model=settings.gemini_model,
        vision=True,
        api_key=settings.google_api_key,
    )
    return provider if provider.vision or not vision else None


def has_ai() -> bool:
    return get_provider() is not None


def has_vision() -> bool:
    return get_provider(vision=True) is not None


def ai_status() -> dict | None:
    """Display info for the UI, or None when unconfigured."""
    p = get_provider()
    if p is None:
        return None
    return {"id": p.id, "label": p.label, "model": p.model, "vision": p.vision}


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model's text response."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
