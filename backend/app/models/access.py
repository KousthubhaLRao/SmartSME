"""Access control tables: team invites and sign-in attempts.

Neither is tenant data in the usual sense. `Invite` is scoped to a business;
`LoginAttempt` deliberately is not, because it has to be recorded before the
email is known to belong to anyone at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, fk, pk, timestamp


class Invite(Base):
    """A pending invitation to join a business.

    Only the SHA-256 of the token is stored, so a leaked database still cannot
    be used to accept an invitation — the same reasoning as a password hash.
    """

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    #: owner | employee
    role: Mapped[str] = mapped_column(Text, nullable=False, default="employee")
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    invited_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = timestamp()

    @property
    def pending(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > datetime.now()
        )


class LoginAttempt(Base):
    """One row per sign-in attempt, successful or not.

    The lockout is derived from these rows rather than from a counter column, so
    two API processes cannot disagree about the count, and a successful sign-in
    clears the streak simply by being the most recent row.
    """

    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = pk()
    #: Lower-cased. Recorded even when no such account exists, so that probing
    #: for valid addresses is throttled the same as attacking a known one.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str | None] = mapped_column(Text)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = timestamp()
