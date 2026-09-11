"""Request dependencies: resolve the signed session cookie into a tenant."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Business, User
from .config import settings
from .db import get_db
from .security import verify_session_token


@dataclass(slots=True)
class AuthContext:
    user: User
    business: Business


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    session_cookie: Annotated[str | None, Cookie(alias=settings.session_cookie)] = None,
) -> AuthContext | None:
    if not session_cookie:
        return None
    user_id = verify_session_token(session_cookie)
    if not user_id:
        return None
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None
    user = db.scalar(select(User).where(User.id == uid))
    if not user:
        return None
    business = db.scalar(select(Business).where(Business.id == user.business_id))
    if not business:
        return None
    return AuthContext(user=user, business=business)


def require_user(
    ctx: Annotated[AuthContext | None, Depends(get_current_user)],
) -> AuthContext:
    """Guards every authenticated route. 401 lets the SPA redirect to sign-in."""
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    return ctx


CurrentUser = Annotated[AuthContext, Depends(require_user)]
Db = Annotated[Session, Depends(get_db)]
