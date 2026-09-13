"""Invitation tokens.

The raw token is shown to the inviter exactly once, in the response that creates
the invitation, and only its SHA-256 is stored. A token is high-entropy random
rather than a password, so a plain hash is enough — there is nothing to brute
force and nothing to salt against.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

#: How long an invitation stays usable.
INVITE_TTL = timedelta(days=7)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()


def default_expiry() -> datetime:
    return datetime.now() + INVITE_TTL


def join_url(base: str, token: str) -> str:
    """The link the inviter sends. There is no mail transport here, so the
    invitation travels however the business already talks to its staff."""
    return f"{base.rstrip('/')}/join/{token}"
