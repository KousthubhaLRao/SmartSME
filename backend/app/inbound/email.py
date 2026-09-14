"""Collecting orders from a mailbox.

Two protocols, because the two situations differ:

* **POP3** is what Mailpit speaks, so `docker compose up -d` gives you a working
  inbox locally with nothing to sign up for. Mail sent to
  `orders+<token>@smartsme.local` on port 1025 is collected on port 1110.
* **IMAP** is what a real mailbox speaks — Gmail, Zoho, a company server. Same
  routing, same parsing.

Both are stdlib (`poplib`, `imaplib`), so no dependency was added for this.

Routing is by plus-address: the business's `inbox_token` goes in the local part,
`orders+7f3a...@your-domain`. It is a shared secret in the same sense a calendar
subscription URL is — anyone who has it can put a *draft* in the queue, and a
person still has to accept it before anything is recorded.
"""

from __future__ import annotations

import contextlib
import email
import imaplib
import logging
import poplib
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime

from ..core.config import settings
from .pipeline import IncomingMessage

log = logging.getLogger("smartsme.inbound.email")

#: A mailbox that stops responding must not wedge the sweep: it shares a
#: thread with the event tick, so a hung socket would stop event processing too.
MAIL_TIMEOUT = 15

#: orders+<token>@domain — the token is what routes the mail.
_PLUS_ADDRESS = re.compile(r"\+([0-9a-z]{6,64})@", re.IGNORECASE)


def _decoded(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_of(message: Message) -> str:
    """The plain-text part. HTML-only mail is reduced to its text."""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                return _payload(part)
        for part in message.walk():
            if part.get_content_type() == "text/html":
                return _strip_html(_payload(part))
        return ""
    if message.get_content_type() == "text/html":
        return _strip_html(_payload(message))
    return _payload(message)


def _payload(part: Message) -> str:
    raw = part.get_payload(decode=True)
    if raw is None:
        return str(part.get_payload() or "")
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text)


def _token_for(message: Message) -> str | None:
    """The inbox token, from whichever recipient header carries it."""
    for header in ("Delivered-To", "X-Original-To", "To", "Cc", "Envelope-To"):
        for value in message.get_all(header, []):
            found = _PLUS_ADDRESS.search(value or "")
            if found:
                return found.group(1).lower()
    return None


def _received_at(message: Message) -> datetime | None:
    raw = message.get("Date")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    # Timestamps in this app are naive local time.
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def to_incoming(raw: bytes, fallback_id: str) -> IncomingMessage | None:
    """Parse one RFC-822 message into the shape the pipeline takes."""
    try:
        message = email.message_from_bytes(raw)
    except Exception:
        log.exception("could not parse a message")
        return None

    sender_name, sender = parseaddr(_decoded(message.get("From")))
    return IncomingMessage(
        channel="email",
        external_id=(message.get("Message-ID") or fallback_id).strip()[:400],
        sender=sender or "",
        sender_name=sender_name or None,
        subject=_decoded(message.get("Subject")) or None,
        body=_body_of(message),
        received_at=_received_at(message),
        token=_token_for(message),
    )


def fetch() -> list[IncomingMessage]:
    """Collect everything waiting, using whichever protocol is configured."""
    if not settings.email_ingest_enabled:
        return []
    if settings.email_protocol == "imap":
        return _fetch_imap()
    return _fetch_pop3()


def _fetch_pop3() -> list[IncomingMessage]:
    """Mailpit and classic POP3 servers. Messages are deleted after collection,
    which is what makes POP3 a queue."""
    out: list[IncomingMessage] = []
    try:
        client = (
            poplib.POP3_SSL(settings.email_host, settings.email_port, timeout=MAIL_TIMEOUT)
            if settings.email_ssl
            else poplib.POP3(settings.email_host, settings.email_port, timeout=MAIL_TIMEOUT)
        )
    except OSError as err:
        log.warning(
            "mailbox unreachable at %s:%s (%s)", settings.email_host, settings.email_port, err
        )
        return out

    try:
        client.user(settings.email_user)
        client.pass_(settings.email_password)
        count = len(client.list()[1])
        for index in range(1, min(count, settings.email_batch) + 1):
            raw = b"\n".join(client.retr(index)[1])
            parsed = to_incoming(raw, fallback_id=f"pop3-{index}-{datetime.now().timestamp()}")
            if parsed:
                out.append(parsed)
            client.dele(index)
    except poplib.error_proto as err:
        log.warning("POP3 error: %s", err)
    finally:
        try:
            client.quit()
        except Exception:
            client.close()
    return out


def _fetch_imap() -> list[IncomingMessage]:
    """A real mailbox. Collected mail is marked read rather than deleted, so the
    user keeps their copy."""
    out: list[IncomingMessage] = []
    try:
        client = (
            imaplib.IMAP4_SSL(settings.email_host, settings.email_port, timeout=MAIL_TIMEOUT)
            if settings.email_ssl
            else imaplib.IMAP4(settings.email_host, settings.email_port, timeout=MAIL_TIMEOUT)
        )
    except OSError as err:
        log.warning(
            "mailbox unreachable at %s:%s (%s)", settings.email_host, settings.email_port, err
        )
        return out

    try:
        client.login(settings.email_user, settings.email_password)
        client.select(settings.email_folder)
        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            return out
        for number in (data[0].split() or [])[: settings.email_batch]:
            status, payload = client.fetch(number, "(RFC822)")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue
            parsed = to_incoming(payload[0][1], fallback_id=f"imap-{number.decode()}")
            if parsed:
                out.append(parsed)
            client.store(number, "+FLAGS", "\\Seen")
    except imaplib.IMAP4.error as err:
        log.warning("IMAP error: %s", err)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    return out
