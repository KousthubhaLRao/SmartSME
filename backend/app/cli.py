"""Small admin commands.

Platform accounts deliberately have no sign-up route — a superuser can read and
change every business on the instance, so creating one is an operator action
taken at the console, not something reachable over HTTP.

    python -m app.cli create-platform-user --role superuser --email me@example.com
    python -m app.cli list-platform-users

The rest are for the inbound channels, which are otherwise awkward to try: one
prints the addresses a business receives orders on, one posts a test order to
the local mail server, and one checks that a Telegram bot token actually works.

    python -m app.cli inbox-token
    python -m app.cli send-test-order "Please send 12 bags rice to Anita Stores"
    python -m app.cli check-telegram
    python -m app.cli ocr-test
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import sys

from sqlalchemy import select

from .core.config import settings
from .core.db import SessionLocal
from .core.roles import ADMIN, PLATFORM_ROLES, SUPERUSER
from .core.security import hash_password
from .models import Business, User


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


def _businesses(name: str | None) -> list[Business]:
    with SessionLocal() as db:
        listing = select(Business).order_by(Business.created_at)
        if name:
            listing = listing.where(Business.name.ilike(f"%{name}%"))
        return list(db.scalars(listing))


def inbox_token(name: str | None) -> int:
    """Where a business receives orders from outside."""
    rows = _businesses(name)
    if not rows:
        print("No businesses found. Start the API once to seed the demo.", file=sys.stderr)
        return 1
    for business in rows:
        print(f"{business.name}")
        print(f"  token     {business.inbox_token}")
        print(f"  email     orders+{business.inbox_token}@{settings.inbox_domain}")
        print(f"  telegram  /link {business.inbox_token}")
        print()
    return 0


def send_test_order(
    text: str, name: str | None, sender: str, subject: str, host: str, port: int
) -> int:
    """Post an order to the local mail server, as a customer would.

    Mailpit is a sink with no compose screen, so without this the only way to
    try inbound email is to write the SMTP call yourself. It is the same mail a
    real customer sends: a From, a Subject, a body, and the plus-address that
    says which shop it belongs to.
    """
    import smtplib
    import uuid as _uuid
    from email.message import EmailMessage

    rows = _businesses(name)
    if not rows:
        print("No businesses found. Start the API once to seed the demo.", file=sys.stderr)
        return 1
    business = rows[0]
    to = f"orders+{business.inbox_token}@{settings.inbox_domain}"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = f"<{_uuid.uuid4().hex}@smartsme.cli>"
    message.set_content(text)

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.send_message(message)
    except OSError as err:
        print(f"Could not reach the mail server at {host}:{port} ({err}).", file=sys.stderr)
        print("Is Mailpit running?  docker compose up -d mailpit", file=sys.stderr)
        return 1

    print(f"Sent to {business.name}")
    print(f"  to       {to}")
    print(f"  body     {text}")
    print()
    print("Now open the Inbox page and press Check now (or wait for the poll).")
    print("The raw mail is at http://localhost:8025")
    if not settings.email_ingest_enabled:
        print()
        print("NOTE: EMAIL_INGEST_ENABLED is off, so nothing will collect it.")
        print("      Restart with:  .\\run-dev.ps1 -WithEmail")
    return 0


def check_telegram() -> int:
    """Confirm the bot token works, and say what to do with it."""
    import httpx

    if not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN is not set in backend/.env.")
        print()
        print("To get one, in the Telegram app:")
        print("  1. open a chat with @BotFather")
        print("  2. send /newbot, pick a display name, then a username ending in 'bot'")
        print("  3. it replies with a token like 123456789:AAE...; put it in backend/.env as")
        print('     TELEGRAM_BOT_TOKEN="123456789:AAE..."')
        return 1

    try:
        response = httpx.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe", timeout=15
        )
        payload = response.json()
    except Exception as err:
        print(f"Could not reach Telegram: {err}", file=sys.stderr)
        return 1

    if not payload.get("ok"):
        print(f"Telegram rejected the token: {payload.get('description')}", file=sys.stderr)
        return 1

    bot = payload["result"]
    print(f"Bot is live: @{bot['username']} ({bot.get('first_name')})")
    print(f"  open       https://t.me/{bot['username']}")
    rows = _businesses(None)
    if rows:
        print(f"  then send  /link {rows[0].inbox_token}")
        print(f"             (links the chat to {rows[0].name})")
    print()
    print("After linking, anything you send that chat becomes a draft on the Inbox page.")
    return 0


def _utf8_console() -> None:
    """Let this terminal print Devanagari and Kannada.

    A Windows console still defaults to cp1252, which cannot encode either
    script - so echoing back the order someone just typed killed the command
    with a UnicodeEncodeError after it had already sent the mail. Modern
    terminals render UTF-8 correctly; older ones now show a placeholder
    character instead of raising.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            # An exotic or already-detached stream may refuse; not worth failing
            # a command over.
            with contextlib.suppress(OSError, ValueError):
                stream.reconfigure(encoding="utf-8", errors="replace")


def ocr_test(paths: list[str], prepare_only: bool) -> int:
    """Run real order slips through OCR and print exactly what came back.

    The point is to find out what an engine can actually do with a photograph
    somebody took on a phone, rather than reasoning about it. Nothing is
    written anywhere and no draft is built - this is the measurement step.
    """
    from pathlib import Path

    from .ai import ocr_space

    files: list[Path] = []
    for raw_path in paths or ["tests/fixtures"]:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES))
        elif path.exists():
            files.append(path)
        else:
            print(f"No such file: {path}", file=sys.stderr)
            return 1

    if not files:
        print("No images found.", file=sys.stderr)
        return 1

    if not prepare_only and not ocr_space.enabled():
        print("OCR_SPACE_API_KEY is not set in backend/.env.")
        print()
        print("Get a free key (no card) at https://ocr.space/ocrapi, then add:")
        print('  OCR_SPACE_API_KEY="K81234567890"')
        print()
        print("Or pass --prepare-only to check the image preparation without a key.")
        return 1

    failures = 0
    for path in files:
        original = path.read_bytes()
        print("=" * 72)
        print(f"{path.name}   {len(original) / 1024:.0f} KB")
        try:
            prepared = ocr_space.prepare(original)
        except Exception as err:
            print(f"  could not prepare: {err}")
            failures += 1
            continue

        fits = "ok" if len(prepared) <= ocr_space.MAX_UPLOAD else "STILL TOO BIG"
        print(f"  prepared: {len(prepared) / 1024:.0f} KB ({fits} for the 1 MB free tier)")
        if prepare_only:
            continue

        try:
            text = ocr_space.read_text(original, filename=path.name)
        except ocr_space.OcrUnavailable as err:
            print(f"  FAILED: {err}")
            failures += 1
            continue

        if not text:
            print("  (no text found)")
            failures += 1
            continue
        for line in text.splitlines():
            if line.strip():
                print(f"  | {line.rstrip()}")

    print("=" * 72)
    done = len(files) - failures
    print(f"{done}/{len(files)} " + ("ready to upload" if prepare_only else "produced text"))
    return 0


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
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

    token = sub.add_parser("inbox-token", help="Show where a business receives orders.")
    token.add_argument("--business", default=None, help="Match part of the name.")

    mail = sub.add_parser("send-test-order", help="Post an order to the local mail server.")
    mail.add_argument("text", help="The order, as a customer would write it.")
    mail.add_argument("--business", default=None)
    mail.add_argument("--from", dest="sender", default="Anita <anita@example.com>")
    mail.add_argument("--subject", default="Order")
    mail.add_argument("--smtp-host", default="localhost")
    mail.add_argument("--smtp-port", type=int, default=1025, help="Mailpit's SMTP port.")

    sub.add_parser("check-telegram", help="Verify TELEGRAM_BOT_TOKEN and print next steps.")

    ocr = sub.add_parser("ocr-test", help="Run order slip images through OCR and show the text.")
    ocr.add_argument("paths", nargs="*", help="Images or a directory (default: tests/fixtures).")
    ocr.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only check the images can be prepared for upload; makes no API call.",
    )

    args = parser.parse_args(argv)
    if args.command == "create-platform-user":
        return create_platform_user(args.email, args.name, args.role, args.password)
    if args.command == "inbox-token":
        return inbox_token(args.business)
    if args.command == "send-test-order":
        return send_test_order(
            args.text, args.business, args.sender, args.subject, args.smtp_host, args.smtp_port
        )
    if args.command == "check-telegram":
        return check_telegram()
    if args.command == "ocr-test":
        return ocr_test(args.paths, args.prepare_only)
    return list_platform_users()


if __name__ == "__main__":
    raise SystemExit(main())
