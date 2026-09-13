"""The people in a business: members and pending invitations.

Everything here needs `users:manage`, which only an owner and a superuser hold.
An admin can reconfigure a business but not decide who works in it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from ..core.deps import CurrentUser, Db, require
from ..core.roles import INVITABLE_ROLES, OWNER, ROLE_LABELS, P
from ..invites import default_expiry, hash_token, join_url, new_token
from ..models import Invite, User
from ..schemas import InviteInput

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(require(P.USERS_MANAGE))],
)


def _member(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "roleLabel": ROLE_LABELS.get(user.role, user.role),
        "createdAt": user.created_at.isoformat(),
    }


def _invite(invite: Invite) -> dict:
    return {
        "id": str(invite.id),
        "email": invite.email,
        "role": invite.role,
        "roleLabel": ROLE_LABELS.get(invite.role, invite.role),
        "expiresAt": invite.expires_at.isoformat(),
        "createdAt": invite.created_at.isoformat(),
    }


@router.get("")
def list_team(ctx: CurrentUser, db: Db) -> dict:
    members = list(
        db.scalars(
            select(User).where(User.business_id == ctx.business.id).order_by(User.created_at)
        )
    )
    invites = list(
        db.scalars(
            select(Invite)
            .where(
                Invite.business_id == ctx.business.id,
                Invite.accepted_at.is_(None),
                Invite.revoked_at.is_(None),
                Invite.expires_at > datetime.now(),
            )
            .order_by(Invite.created_at.desc())
        )
    )
    return {
        "members": [_member(u) for u in members],
        "invites": [_invite(i) for i in invites],
        "roles": [{"value": r, "label": ROLE_LABELS[r]} for r in INVITABLE_ROLES],
    }


@router.post("/invites", status_code=201)
def create_invite(body: InviteInput, ctx: CurrentUser, db: Db, request: Request) -> dict:
    """Mint an invitation and return the join link.

    The raw token appears in this response and nowhere else — there is no mail
    transport here, so the owner copies the link and sends it however they
    already reach their staff.
    """
    if body.role not in INVITABLE_ROLES:
        raise HTTPException(status_code=400, detail="Role must be owner or employee.")

    email = body.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="That email already has an account.")

    existing = db.scalar(
        select(Invite).where(
            Invite.email == email,
            Invite.business_id == ctx.business.id,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > datetime.now(),
        )
    )
    if existing is not None:
        # Re-inviting should replace the old link rather than leave two live.
        existing.revoked_at = datetime.now()

    token = new_token()
    invite = Invite(
        business_id=ctx.business.id,
        email=email,
        role=body.role,
        token_hash=hash_token(token),
        invited_by=ctx.user.id,
        expires_at=default_expiry(),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    origin = request.headers.get("origin") or str(request.base_url)
    return {**_invite(invite), "token": token, "joinUrl": join_url(origin, token)}


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    invite = db.scalar(
        select(Invite).where(Invite.id == invite_id, Invite.business_id == ctx.business.id)
    )
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    invite.revoked_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.put("/{user_id}/role")
def set_role(user_id: uuid.UUID, body: InviteInput, ctx: CurrentUser, db: Db) -> dict:
    """Promote or demote a member. Reuses InviteInput for its `role` field."""
    if body.role not in INVITABLE_ROLES:
        raise HTTPException(status_code=400, detail="Role must be owner or employee.")
    user = _member_or_404(db, ctx, user_id)
    if user.id == ctx.user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")
    if user.role == OWNER and body.role != OWNER:
        _guard_last_owner(db, ctx, user)
    user.role = body.role
    db.commit()
    return _member(user)


@router.delete("/{user_id}")
def remove_member(user_id: uuid.UUID, ctx: CurrentUser, db: Db) -> dict:
    user = _member_or_404(db, ctx, user_id)
    if user.id == ctx.user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself.")
    if user.role == OWNER:
        _guard_last_owner(db, ctx, user)
    db.delete(user)
    db.commit()
    return {"ok": True}


def _member_or_404(db: Db, ctx: CurrentUser, user_id: uuid.UUID) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.business_id == ctx.business.id))
    if user is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    return user


def _guard_last_owner(db: Db, ctx: CurrentUser, user: User) -> None:
    """A business with no owner could never be administered again."""
    owners = db.scalar(
        select(User.id)
        .where(User.business_id == ctx.business.id, User.role == OWNER, User.id != user.id)
        .limit(1)
    )
    if owners is None:
        raise HTTPException(status_code=400, detail="A business must keep at least one owner.")
