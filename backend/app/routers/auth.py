"""Sign-up / sign-in / sign-out, the session probe, and accepting an invite."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..core.config import settings
from ..core.deps import AuthContext, Db, SessionUser
from ..core.roles import OWNER, ROLE_LABELS, permissions_for
from ..core.security import create_session_token, hash_password, verify_password
from ..core.throttle import check_sign_in_allowed, client_ip, record_attempt
from ..invites import hash_token
from ..models import Business, Invite, User
from ..schemas import AcceptInviteInput, SignInInput, SignUpInput
from ..workflow import default_rules

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie,
        value=create_session_token(user_id),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
    )


def _me(ctx: AuthContext) -> dict:
    """The session payload the SPA boots from.

    `business` is null for a platform role, which has none of its own; the
    client uses that to show the business picker instead of the app shell.
    """
    b = ctx.business
    return {
        "user": {
            "id": str(ctx.user.id),
            "name": ctx.user.name,
            "email": ctx.user.email,
            "role": ctx.user.role,
            "roleLabel": ROLE_LABELS.get(ctx.user.role, ctx.user.role),
        },
        "permissions": sorted(permissions_for(ctx.user.role)),
        "business": None
        if b is None
        else {
            "id": str(b.id),
            "name": b.name,
            "currency": b.currency,
            "taxRate": b.tax_rate,
            "invoicePrefix": b.invoice_prefix,
            "gstNumber": b.gst_number,
            "panNumber": b.pan_number,
            "address": b.address,
            "phone": b.phone,
            "email": b.email,
        },
    }


def _with_business(db: Db, user: User) -> AuthContext:
    business = (
        db.scalar(select(Business).where(Business.id == user.business_id))
        if user.business_id
        else None
    )
    return AuthContext(user=user, business=business)


@router.post("/sign-in")
def sign_in(body: SignInInput, request: Request, response: Response, db: Db) -> dict:
    email = body.email.strip().lower()
    ip = client_ip(request)

    # Before the password is checked, so a locked account costs an attacker a
    # round-trip and nothing else.
    check_sign_in_allowed(db, email, ip)

    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        record_attempt(db, email, ip, successful=False)
        # One message for both cases, so the response cannot enumerate accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
        )

    record_attempt(db, email, ip, successful=True)
    _set_cookie(response, str(user.id))
    return _me(_with_business(db, user))


@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUpInput, response: Response, db: Db) -> dict:
    """Create a business and its first owner.

    This is the only way an `owner` appears without an invitation, and it never
    creates a platform role — those are made with `python -m app.cli`.
    """
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    email = body.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    business = Business(name=body.businessName.strip() or "My Business")
    db.add(business)
    db.flush()

    user = User(
        business_id=business.id,
        email=email,
        name=body.name.strip() or "Owner",
        password_hash=hash_password(body.password),
        role=OWNER,
    )
    db.add(user)
    db.add_all(default_rules(business.id))
    db.commit()
    db.refresh(user)
    db.refresh(business)

    _set_cookie(response, str(user.id))
    return _me(AuthContext(user=user, business=business))


@router.get("/invite/{token}")
def preview_invite(token: str, db: Db) -> dict:
    """What the join page shows before the invitee commits to anything."""
    invite = db.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
    if invite is None or not invite.pending:
        raise HTTPException(status_code=404, detail="This invitation is no longer valid.")
    business = db.scalar(select(Business).where(Business.id == invite.business_id))
    return {
        "email": invite.email,
        "role": invite.role,
        "roleLabel": ROLE_LABELS.get(invite.role, invite.role),
        "businessName": business.name if business else "",
    }


@router.post("/accept-invite", status_code=status.HTTP_201_CREATED)
def accept_invite(body: AcceptInviteInput, response: Response, db: Db) -> dict:
    """Turn a valid invitation into an account, and sign the new user in."""
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    invite = db.scalar(select(Invite).where(Invite.token_hash == hash_token(body.token)))
    if invite is None or not invite.pending:
        raise HTTPException(status_code=404, detail="This invitation is no longer valid.")
    if db.scalar(select(User.id).where(User.email == invite.email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        business_id=invite.business_id,
        email=invite.email,
        name=body.name.strip() or invite.email.split("@")[0],
        password_hash=hash_password(body.password),
        role=invite.role,
    )
    db.add(user)
    invite.accepted_at = datetime.now()
    db.commit()
    db.refresh(user)

    _set_cookie(response, str(user.id))
    return _me(_with_business(db, user))


@router.post("/sign-out")
def sign_out(response: Response) -> dict:
    response.delete_cookie(settings.session_cookie, path="/")
    return {"ok": True}


@router.get("/me")
def me(ctx: SessionUser, db: Db) -> dict:
    """Tolerates a platform role with no business of its own."""
    if ctx.business is None and ctx.user.business_id is not None:
        ctx = _with_business(db, ctx.user)
    return _me(ctx)
