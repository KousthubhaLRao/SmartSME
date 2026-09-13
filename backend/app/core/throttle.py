"""Sign-in throttling.

Two independent limits:

* **Per account.** Five failures inside the lookback window lock the address for
  fifteen minutes, and every further five doubles it, up to a day. A successful
  sign-in ends the streak.
* **Per IP.** A much larger budget across *all* addresses, which is what catches
  password spraying — one guess each against a hundred accounts never trips the
  per-account limit.

Employees are exempt from the per-account lock, by design: their accounts are a
poor target and locking one strands a shopkeeper's staff at the counter. They
are still covered by the per-IP limit.

An unknown email is throttled exactly like a real one. That costs nothing and
means the lockout response cannot be used to tell which addresses have accounts
— except that it does distinguish an *employee* from everything else, which is
the price of the exemption above.

State lives in Postgres rather than in memory so that two API processes agree,
and so a restart does not hand an attacker a fresh budget. Moving it to Redis
later means reimplementing `_failure_streak` and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import LoginAttempt, User
from .config import settings
from .roles import THROTTLED_ROLES

#: Failures older than this never count, however many there are.
LOOKBACK = timedelta(hours=24)
#: How long attempt rows are kept before the sweep removes them.
RETENTION = timedelta(days=7)
MAX_LOCK = timedelta(hours=24)
#: Enough doublings to pass MAX_LOCK from any sane starting point; keeps the
#: exponent small enough to be an int.
_MAX_DOUBLINGS = 12


def client_ip(request: Request) -> str | None:
    """The caller's address, honouring one layer of reverse proxy.

    `X-Forwarded-For` is trivially spoofable when the app is exposed directly,
    so this only ever tightens the limit for honest callers; the per-account
    limit is the one that does not depend on it.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:100]
    return request.client.host if request.client else None


def _failure_streak(db: Session, email: str) -> tuple[int, datetime | None]:
    """Failures since the last successful sign-in, and when the last one was."""
    rows = list(
        db.scalars(
            select(LoginAttempt)
            .where(
                LoginAttempt.email == email,
                LoginAttempt.created_at >= datetime.now() - LOOKBACK,
            )
            .order_by(LoginAttempt.created_at.desc())
            .limit(100)
        )
    )
    failures = 0
    last: datetime | None = None
    for row in rows:
        if row.successful:
            break
        failures += 1
        if last is None:
            last = row.created_at
    return failures, last


def _lock_expiry(failures: int, last_failure: datetime | None) -> datetime | None:
    """When the current lock ends, or None if there is no lock."""
    threshold = settings.login_max_attempts
    if last_failure is None or failures < threshold:
        return None
    # Every further `threshold` failures doubles the wait. The exponent is
    # capped before it is used: a bot that has made thousands of attempts would
    # otherwise overflow the shift long before MAX_LOCK could clamp the result.
    blocks = min(failures // threshold, _MAX_DOUBLINGS)
    lock = min(
        timedelta(minutes=settings.login_lock_minutes) * (2 ** (blocks - 1)),
        MAX_LOCK,
    )
    return last_failure + lock


def _ip_failures(db: Session, ip: str | None) -> int:
    """Failed attempts from one address across every account in the window."""
    if not ip:
        return 0
    window = datetime.now() - timedelta(minutes=settings.login_window_minutes)
    return (
        db.scalar(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.ip == ip,
                LoginAttempt.successful.is_(False),
                LoginAttempt.created_at >= window,
            )
        )
        or 0
    )


def _too_many(retry_after: timedelta) -> HTTPException:
    seconds = max(1, int(retry_after.total_seconds()))
    minutes = max(1, round(seconds / 60))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many sign-in attempts. Try again in about {minutes} minute(s).",
        headers={"Retry-After": str(seconds)},
    )


def check_sign_in_allowed(db: Session, email: str, ip: str | None) -> None:
    """Raise 429 when this email or IP has spent its budget.

    Called before the password is checked, and a rejected call is not recorded —
    hammering a locked account does not extend the lock.
    """
    if _ip_failures(db, ip) >= settings.login_max_ip_attempts:
        raise _too_many(timedelta(minutes=settings.login_window_minutes))

    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.role not in THROTTLED_ROLES:
        return  # employee: per-IP limit only

    failures, last_failure = _failure_streak(db, email)
    expiry = _lock_expiry(failures, last_failure)
    if expiry is not None and datetime.now() < expiry:
        raise _too_many(expiry - datetime.now())


def record_attempt(db: Session, email: str, ip: str | None, *, successful: bool) -> None:
    """Append the outcome, and sweep rows too old to matter."""
    db.add(LoginAttempt(email=email, ip=ip, successful=successful))
    if successful:
        db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < datetime.now() - RETENTION))
    db.commit()
