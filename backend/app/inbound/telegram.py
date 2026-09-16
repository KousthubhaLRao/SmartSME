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

**Long polling**, not webhooks: `getUpdates` works from a laptop behind NAT
with nothing to expose. The offset lives in memory, so a restart re-reads
whatever Telegram still holds; that is harmless, because ingestion deduplicates
on the message id and a re-read message is recognised rather than queued twice.
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
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 409:
            # Telegram lets exactly one process poll a bot. A second one - a
            # teammate running their own copy against the same token - does not
            # share the stream, it competes for it, and each side gets a random
            # half of the messages. Worth naming, because the symptom is
            # "some orders never arrive" and the cause is nowhere near the app.
            log.error(
                "Another process is already polling this Telegram bot. Messages will be "
                "split between them at random. Use one bot per running copy, or run only "
                "one copy at a time."
            )
        else:
            log.warning("telegram getUpdates failed: %s", err)
        return []
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


#: Telegram will hand over a file this large; anything bigger is refused rather
#: than downloaded, because the app's own upload limit is 8 MB and a photograph
#: of a slip has no business being larger.
MAX_PHOTO_BYTES = 8 * 1024 * 1024

#: What the bot can read as a picture of an order.
PHOTO_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def photo_in(message: dict) -> tuple[str, str] | None:
    """The file id and media type of a photographed order, if there is one.

    Telegram delivers the same picture two ways. Sent as a **photo** it arrives
    as `photo[]`, several recompressed sizes, largest last - that is what the
    phone camera button produces. Sent as a **file** it arrives as `document`
    with its original bytes, which is what somebody picking the paperclip and
    choosing "File" gets, and it is the better one to read.
    """
    document = message.get("document") or {}
    mime = (document.get("mime_type") or "").lower()
    if document.get("file_id") and mime in PHOTO_MIME:
        if (document.get("file_size") or 0) <= MAX_PHOTO_BYTES:
            return document["file_id"], mime
        log.warning("telegram document too large to read: %s bytes", document.get("file_size"))
        return None

    sizes = message.get("photo") or []
    if sizes:
        # Last is the largest Telegram kept; a smaller one would lose the
        # handwriting we are trying to read.
        for size in reversed(sizes):
            if size.get("file_id") and (size.get("file_size") or 0) <= MAX_PHOTO_BYTES:
                return size["file_id"], "image/jpeg"
    return None


def download(file_id: str) -> bytes | None:
    """Fetch a file the bot was sent. None when Telegram will not give it up."""
    if not enabled():
        return None
    try:
        lookup = httpx.get(_url("getFile"), params={"file_id": file_id}, timeout=20)
        lookup.raise_for_status()
        payload = lookup.json()
        if not payload.get("ok"):
            log.warning("telegram refused getFile: %s", payload.get("description"))
            return None
        file_path = (payload.get("result") or {}).get("file_path")
        if not file_path:
            return None
        blob = httpx.get(
            f"{API}/file/bot{settings.telegram_bot_token}/{file_path}",
            timeout=60,
            follow_redirects=True,
        )
        blob.raise_for_status()
    except (httpx.HTTPError, ValueError) as err:
        log.warning("telegram file download failed: %s", err)
        return None
    if len(blob.content) > MAX_PHOTO_BYTES:
        log.warning("telegram file larger than expected: %s bytes", len(blob.content))
        return None
    return blob.content


def to_incoming(update: dict) -> IncomingMessage | None:
    """One Telegram update as the pipeline's shape, or None if there is nothing
    in it to read - neither text nor a picture."""
    message = update.get("message") or {}
    text = (message.get("text") or message.get("caption") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None

    photo = photo_in(message)
    if not text and photo is None:
        return None

    sender = message.get("from") or {}
    handle = sender.get("username")
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or None

    image: bytes | None = None
    media_type = "image/jpeg"
    if photo is not None:
        # Downloaded here rather than later so a picture Telegram will not hand
        # over is treated as "no picture" before anything is stored: a queued
        # message whose image never arrived is worse than one that never queued.
        image = download(photo[0])
        if image is None and not text:
            return None
        media_type = photo[1]

    return IncomingMessage(
        channel="telegram",
        external_id=str(chat_id),
        sender=f"@{handle}" if handle else str(sender.get("id") or chat_id),
        sender_name=name,
        subject=None,
        body=text,
        image=image,
        image_media_type=media_type,
    )
