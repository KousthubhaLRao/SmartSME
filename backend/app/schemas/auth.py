"""Sign-in and sign-up payloads."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class SignInInput(BaseModel):
    email: EmailStr
    password: str


class SignUpInput(BaseModel):
    """Creates the business and its first owner user in one step."""

    businessName: str
    name: str
    email: EmailStr
    password: str


class InviteInput(BaseModel):
    """An invitation an owner hands out. `role` must be owner or employee."""

    email: EmailStr
    role: str = "employee"


class AcceptInviteInput(BaseModel):
    """Turning an invitation into an account."""

    token: str
    name: str
    password: str
