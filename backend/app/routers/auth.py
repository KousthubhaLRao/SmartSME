"""Sign-up / sign-in / sign-out and the current-session probe."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from ..core.config import settings
from ..core.deps import AuthContext, CurrentUser, Db
from ..core.security import create_session_token, hash_password, verify_password
from ..models import Business, User
from ..schemas import SignInInput, SignUpInput
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
    return {
        "user": {
            "id": str(ctx.user.id),
            "name": ctx.user.name,
            "email": ctx.user.email,
            "role": ctx.user.role,
        },
        "business": {
            "id": str(ctx.business.id),
            "name": ctx.business.name,
            "currency": ctx.business.currency,
            "taxRate": ctx.business.tax_rate,
            "invoicePrefix": ctx.business.invoice_prefix,
            "gstNumber": ctx.business.gst_number,
            "panNumber": ctx.business.pan_number,
            "address": ctx.business.address,
            "phone": ctx.business.phone,
            "email": ctx.business.email,
        },
    }


@router.post("/sign-in")
def sign_in(body: SignInInput, response: Response, db: Db) -> dict:
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        # One message for both cases, so the response cannot enumerate accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
        )
    business = db.scalar(select(Business).where(Business.id == user.business_id))
    if business is None:
        raise HTTPException(status_code=500, detail="Account is missing its business.")
    _set_cookie(response, str(user.id))
    return _me(AuthContext(user=user, business=business))


@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUpInput, response: Response, db: Db) -> dict:
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
        role="owner",
    )
    db.add(user)
    db.add_all(default_rules(business.id))
    db.commit()
    db.refresh(user)
    db.refresh(business)

    _set_cookie(response, str(user.id))
    return _me(AuthContext(user=user, business=business))


@router.post("/sign-out")
def sign_out(response: Response) -> dict:
    response.delete_cookie(settings.session_cookie, path="/")
    return {"ok": True}


@router.get("/me")
def me(ctx: CurrentUser) -> dict:
    return _me(ctx)
