"""Collecting orders from Telegram.

Telegram is the one mainstream messenger with a genuinely free, instantly
self-issued API key: message @BotFather, send `/newbot`, get a token. No card,
no business verification, no approval queue — which is why it is the channel
wired up here.

**Linking.** Telegram cannot know which shop a chat belongs to, so the owner
sends the bot `/link <token>` once, with the inbox token from Settings. That
binds the chat; every later message from it is routed to that business. Any
message from an unlinked chat gets a short reply explaining how to link, and is
otherwise ignored.

**Long polling**, not webhooks: `getUpdates` works from a laptop behind NAT with
nothing to expose. The offset is stored in the database so a restart does not
re-read the backlog, and Telegram itself acknowledges by offset, so the same
update is never processed twice.
"""

from __future__ import annotations

import logging

import httpx

from ..core.config import settings
from .pipeline import IncomingMessage

log = logging.getLogger("smartsme.inbound.telegram")

API = "https://api.telegram.org"


def enabled() -> bool:
    return bool(settings.telegram_bot_token)


def _url(method: str) -> str:
    return f"{API}/bot{settings.telegram_bot_token}/{method}"


def get_updates(offset: int | None = None, timeout: int = 0) -> list[dict]:
    """Poll for new updates. `timeout=0` returns immediately, which is what the
    periodic sweep wants; a worker loop can pass a longer timeout."""
    if not enabled():
        return []
    params: dict[str, object] = {"timeout": timeout, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    try:
        response = httpx.get(_url("getUpdates"), params=params, timeout=timeout + 15)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as err:
        log.warning("telegram getUpdates failed: %s", err)
        return []
    if not payload.get("ok"):
        log.warning("telegram refused getUpdates: %s", payload.get("description"))
        return []
    return payload.get("result") or []


def send_message(chat_id: str | int, text: str) -> bool:
    """Reply in the chat. Best effort — a failed reply must never lose the order
    that prompted it."""
    if not enabled():
        return False
    try:
        response = httpx.post(
            _url("sendMessage"),
            json={"chat_id": chat_id, "text": text, "disable_notification": True},
            timeout=15,
        )
        return response.status_code == 200
    except httpx.HTTPError as err:
        log.warning("telegram sendMessage failed: %s", err)
        return False


def link_token_in(text: str) -> str | None:
    """The token from a `/link <token>` command, if that is what this is."""
    parts = (text or "").strip().split()
    if len(parts) >= 2 and parts[0].lower().lstrip("/").split("@")[0] == "link":
        return parts[1].strip().lower()
    return None


def to_incoming(update: dict) -> IncomingMessage | None:
    """One Telegram update as the pipeline's shape, or None if it carries no
    text worth reading."""
    message = update.get("message") or {}
    text = (message.get("text") or message.get("caption") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not text or chat_id is None:
        return None

    sender = message.get("from") or {}
    handle = sender.get("username")
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or None

    return IncomingMessage(
        channel="telegram",
        external_id=str(chat_id),
        sender=f"@{handle}" if handle else str(sender.get("id") or chat_id),
        sender_name=name,
        subject=None,
        body=text,
    )
