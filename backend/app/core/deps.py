"""Request dependencies: resolve the session cookie into a user, a business and
a set of permissions.

Three layers, each building on the last:

``SessionUser``
    Signed in. The business may be ``None`` — a superuser or admin belongs to
    none. Only the auth routes use this.

``CurrentUser``
    Signed in *and* pointed at a business. Tenant roles get their own; platform
    roles name one with ``?businessId=``. Every tenant route uses this.

``require(...)``
    The same as ``CurrentUser``, plus a permission check. Attach it to a route
    with ``dependencies=[Depends(require(P.DATA_MANAGE))]`` so the handler
    signature stays about the handler's job.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Business, User
from .config import settings
from .db import get_db
from .roles import has_permission, is_platform_role, permissions_for
from .security import verify_session_token


@dataclass(slots=True)
class AuthContext:
    user: User
    #: The business this request acts on. None only for a platform role that has
    #: not named one.
    business: Business | None = None

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.role)

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)

    def require(self, permission: str) -> None:
        """For the handful of checks that depend on the request body rather than
        the route, and so cannot be declared on the decorator."""
        if not self.can(permission):
            raise _forbidden(self.role, permission)


def _forbidden(role: str, permission: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Your role ({role}) is not allowed to do this.",
    )


def get_session(
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
    return AuthContext(user=user)


def require_user(
    ctx: Annotated[AuthContext | None, Depends(get_session)],
) -> AuthContext:
    """Signed in, with or without a business. 401 lets the SPA redirect."""
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    return ctx


def require_tenant(
    ctx: Annotated[AuthContext, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    business_id: Annotated[uuid.UUID | None, Query(alias="businessId")] = None,
) -> AuthContext:
    """Attach the business this request acts on.

    A tenant role is pinned to its own business and may not ask for another. A
    platform role has to name one, because it has none of its own.
    """
    if is_platform_role(ctx.role):
        if business_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Add ?businessId= to say which business this request is for.",
            )
        target = business_id
    else:
        if ctx.user.business_id is None:
            raise HTTPException(status_code=403, detail="Your account has no business.")
        if business_id is not None and business_id != ctx.user.business_id:
            # Deliberately the same answer as a business that does not exist, so
            # the parameter cannot be used to discover other tenants.
            raise HTTPException(status_code=404, detail="Business not found.")
        target = ctx.user.business_id

    business = db.scalar(select(Business).where(Business.id == target))
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found.")
    ctx.business = business
    return ctx


def require(*permissions: str):
    """Build a dependency that admits only roles holding every permission."""

    def guard(ctx: Annotated[AuthContext, Depends(require_tenant)]) -> AuthContext:
        for permission in permissions:
            if not ctx.can(permission):
                raise _forbidden(ctx.role, permission)
        return ctx

    return guard


def require_global(*permissions: str):
    """Like `require`, but for routes that are not about one business — listing
    the tenants, for instance. Checks the permission without resolving a
    business, so it works for a platform role that has not named one."""

    def guard(ctx: Annotated[AuthContext, Depends(require_user)]) -> AuthContext:
        for permission in permissions:
            if not ctx.can(permission):
                raise _forbidden(ctx.role, permission)
        return ctx

    return guard


SessionUser = Annotated[AuthContext, Depends(require_user)]
CurrentUser = Annotated[AuthContext, Depends(require_tenant)]
Db = Annotated[Session, Depends(get_db)]
