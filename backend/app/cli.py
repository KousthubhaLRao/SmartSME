"""Small admin commands.

Platform accounts deliberately have no sign-up route — a superuser can read and
change every business on the instance, so creating one is an operator action
taken at the console, not something reachable over HTTP.

    python -m app.cli create-platform-user --role superuser --email me@example.com
    python -m app.cli list-platform-users
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from .core.db import SessionLocal
from .core.roles import ADMIN, PLATFORM_ROLES, SUPERUSER
from .core.security import hash_password
from .models import User


def create_platform_user(email: str, name: str, role: str, password: str | None) -> int:
    if role not in PLATFORM_ROLES:
        print(f"Role must be one of: {', '.join(sorted(PLATFORM_ROLES))}", file=sys.stderr)
        return 2

    email = email.strip().lower()
    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 2
    if len(password) < 12:
        # Higher bar than the 6 the sign-up form takes: this account can reach
        # every business on the instance.
        print("A platform password must be at least 12 characters.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            print(f"{email} already has an account.", file=sys.stderr)
            return 1
        db.add(
            User(
                business_id=None,
                email=email,
                name=name or email.split("@")[0],
                password_hash=hash_password(password),
                role=role,
            )
        )
        db.commit()
    print(f"Created {role} {email}")
    return 0


def list_platform_users() -> int:
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(User).where(User.role.in_(sorted(PLATFORM_ROLES))).order_by(User.created_at)
            )
        )
    if not rows:
        print("No platform accounts.")
        return 0
    width = max(len(u.email) for u in rows)
    for u in rows:
        print(f"  {u.email.ljust(width)}   {u.role}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-platform-user", help="Create a superuser or admin.")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="")
    create.add_argument("--role", default=SUPERUSER, choices=[SUPERUSER, ADMIN])
    create.add_argument(
        "--password",
        default=None,
        help="Omit to be prompted, which keeps it out of your shell history.",
    )

    sub.add_parser("list-platform-users", help="List superusers and admins.")

    args = parser.parse_args(argv)
    if args.command == "create-platform-user":
        return create_platform_user(args.email, args.name, args.role, args.password)
    return list_platform_users()


if __name__ == "__main__":
    raise SystemExit(main())
