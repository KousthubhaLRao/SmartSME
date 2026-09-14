"""Provider-agnostic AI layer for the Smart Input Engine.

Works with whichever API key is configured, with no code changes to switch:

  - Anthropic  (ANTHROPIC_API_KEY  + ANTHROPIC_MODEL)
  - OpenAI, or ANY OpenAI-compatible endpoint  (OPENAI_API_KEY + OPENAI_BASE_URL)
  - Groq       (GROQ_API_KEY + GROQ_MODEL)
  - Google Gemini (GOOGLE_API_KEY + GEMINI_MODEL)

If several keys are set, AI_PROVIDER picks one; otherwise the first configured
provider in the order above wins. With no key at all, callers fall back to the
built-in heuristic parser.
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
    base_url: str = ""

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
            if self.id == "anthropic":
                out = _anthropic_complete(self, prompt, system, image, max_tokens)
            elif self.id == "google":
                out = _gemini_complete(self, prompt, system, image, max_tokens)
            else:
                out = _openai_complete(self, prompt, system, image, max_tokens)
        except Exception:
            _record_failure()
            raise
        _record_success()
        return out


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
def _anthropic_complete(
    p: AiProvider, prompt: str, system: str | None, image: AiImage | None, max_tokens: int
) -> str:
    content: list[dict] = []
    if image:
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": image.media_type, "data": image.base64},
            }
        )
    content.append({"type": "text", "text": prompt})

    body: dict = {
        "model": p.model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        body["system"] = system

    with httpx.Client(timeout=TIMEOUT) as client:
        res = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": p.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
    if res.status_code >= 400:
        raise RuntimeError(f"AI request failed ({res.status_code}). {res.text[:200]}")
    data = res.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


# ---------------------------------------------------------------------------
# OpenAI / any OpenAI-compatible endpoint (incl. Groq)
# ---------------------------------------------------------------------------
def _openai_complete(
    p: AiProvider, prompt: str, system: str | None, image: AiImage | None, max_tokens: int
) -> str:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    if image:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{image.media_type};base64,{image.base64}"},
                    },
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": prompt})

    base = p.base_url.rstrip("/")
    with httpx.Client(timeout=TIMEOUT) as client:
        res = client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {p.api_key}", "Content-Type": "application/json"},
            json={"model": p.model, "messages": messages, "max_tokens": max_tokens},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"AI request failed ({res.status_code}). {res.text[:200]}")
    data = res.json()
    choices = data.get("choices") or []
    return (choices[0].get("message", {}) or {}).get("content", "") if choices else ""


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def _build(provider_id: str) -> AiProvider | None:
    if provider_id == "anthropic" and settings.anthropic_api_key:
        return AiProvider(
            id="anthropic",
            label="Anthropic Claude",
            model=settings.anthropic_model,
            vision=True,
            api_key=settings.anthropic_api_key,
        )
    if provider_id == "openai" and settings.openai_api_key:
        return AiProvider(
            id="openai",
            label="OpenAI-compatible",
            model=settings.openai_model,
            vision=True,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    if provider_id == "groq" and settings.groq_api_key:
        # Groq offers both text-only and vision models. Only a vision model can
        # do OCR, so we report vision support based on the configured model.
        model = settings.groq_model
        return AiProvider(
            id="groq",
            label="Groq",
            model=model,
            vision=any(tag in model.lower() for tag in ("vision", "scout", "maverick", "llava")),
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
    if provider_id == "google" and settings.google_api_key:
        return AiProvider(
            id="google",
            label="Google Gemini",
            model=settings.gemini_model,
            vision=True,
            api_key=settings.google_api_key,
        )
    return None


ORDER = ("anthropic", "openai", "groq", "google")


def get_provider() -> AiProvider | None:
    """The active provider, or None when no API key is configured."""
    forced = (settings.ai_provider or "").lower().strip()
    if forced in ORDER:
        return _build(forced)
    for pid in ORDER:
        p = _build(pid)
        if p:
            return p
    return None


def has_ai() -> bool:
    return get_provider() is not None


def has_vision() -> bool:
    p = get_provider()
    return p is not None and p.vision


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
