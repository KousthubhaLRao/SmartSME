"""Fixtures for the endpoint smoke tests, and the terminal report.

The API has no embedded-database mode, so these tests need a real Postgres. They
point the app at a scratch `<database>_test` database alongside the configured
one, rebuild it from the Alembic migrations, and leave the development data
untouched. If Postgres is not running the smoke tests skip with a note instead
of failing fifty times over.

The environment has to be set before `app.core.db` is imported, because that
module builds its engine the moment it is loaded — hence the work at import time
rather than inside a fixture.
"""

from __future__ import annotations

import os
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_URL = "postgresql+psycopg://smartsme:smartsme@localhost:5432/smartsme"


def _configured_database_url() -> str:
    """The developer's own DATABASE_URL, from the environment or backend/.env."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return DEFAULT_URL


def _prepare_test_database() -> str | None:
    """Create a clean `<database>_test` and point the app at it.

    Returns the URL, or None when Postgres cannot be reached.
    """
    url = make_url(_configured_database_url())
    test_url = url.set(database=f"{url.database}_test")

    # CREATE/DROP DATABASE cannot run inside a transaction, hence AUTOCOMMIT.
    admin = create_engine(url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with admin.connect() as conn:
            # Dropping first keeps every run identical; the _test suffix means
            # this can never be the database the developer is working in.
            conn.execute(text(f'drop database if exists "{test_url.database}" with (force)'))
            conn.execute(text(f'create database "{test_url.database}"'))
    except SQLAlchemyError:
        return None
    finally:
        admin.dispose()

    os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    # The tests build their own fixtures and assert on exact counts.
    os.environ["SEED_DEMO_DATA"] = "false"
    # No background thread: the write endpoints drain the event queue inline, so
    # effects are visible by the time a request returns.
    os.environ["DISABLE_WORKER"] = "true"
    os.environ["AUTH_SECRET"] = "smartsme-test-secret-" + "0" * 32
    # Keep the suite hermetic: with no provider the Smart Input engine uses its
    # built-in parser and OCR reports itself as unavailable. No network calls.
    os.environ["AI_PROVIDER"] = ""
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY"):
        os.environ[key] = ""
    return os.environ["DATABASE_URL"]


TEST_DATABASE_URL = _prepare_test_database()


@pytest.fixture(scope="session")
def anon():
    """A TestClient with no session cookie, on a freshly migrated database."""
    if TEST_DATABASE_URL is None:
        pytest.skip("Postgres is unreachable. Start it with: docker compose up -d")

    from alembic.config import Config
    from fastapi.testclient import TestClient

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")

    from app.main import app

    # The context manager runs the lifespan, so this also covers startup.
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def client(anon):
    """A signed-in client. Signing up creates the business and its owner."""
    email = f"owner-{uuid.uuid4().hex[:12]}@smoketest.dev"
    r = anon.post(
        "/api/auth/sign-up",
        json={
            "businessName": "Smoke Test Traders",
            "name": "Smoke Owner",
            "email": email,
            "password": "smoke1234",
        },
    )
    assert r.status_code == 201, r.text
    yield anon


@pytest.fixture(scope="session")
def workspace(client) -> dict[str, Any]:
    """A customer, a supplier and a stocked product to transact against."""
    customer = client.post(
        "/api/parties", json={"type": "customer", "name": "Anita Stores", "phone": "9000000001"}
    )
    supplier = client.post(
        "/api/parties", json={"type": "supplier", "name": "ABC Suppliers", "phone": "9000000002"}
    )
    product = client.post(
        "/api/products",
        json={
            "name": "Cooking Oil",
            "sku": "OIL-1L",
            "unit": "litre",
            "purchasePrice": 100,
            "sellingPrice": 140,
            "stock": 50,
            "lowStockThreshold": 5,
        },
    )
    for r in (customer, supplier, product):
        assert r.status_code == 201, r.text
    return {
        "customerId": customer.json()["id"],
        "supplierId": supplier.json()["id"],
        "productId": product.json()["id"],
    }


@pytest.fixture
def fresh_client(anon):
    """A TestClient with its own cookie jar, for tests that sign in or out
    without disturbing the session-scoped `client`."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Terminal report
#
# pytest prints failures first and the counts last, which means after a long
# run the thing you want (what broke) has scrolled away. These hooks invert
# that: a per-file summary at the very end, then the failures underneath it.
# ---------------------------------------------------------------------------

#: Friendly names for the two layers; anything else falls back to its path.
GROUP_NAMES = {
    "tests/test_domain.py": "Domain units",
    "tests/test_api_smoke.py": "Endpoint smoke",
}

OUTCOMES = ("passed", "failed", "error", "skipped", "xfailed", "xpassed")

_failures: list[tuple[str, str]] = []
_skip_reasons: Counter = Counter()
_started_at = 0.0


def _group_of(nodeid: str) -> str:
    path = nodeid.split("::")[0].replace("\\", "/")
    return GROUP_NAMES.get(path, path)


def _describe(counts: Counter) -> str:
    # ASCII only: this goes to a console that may be on a legacy code page.
    return ", ".join(f"{counts[o]} {o}" for o in OUTCOMES if counts[o])


def pytest_sessionstart(session):
    global _started_at
    _started_at = time.time()


def pytest_runtest_logreport(report):
    """Keep the rendered failure while the traceback style is still the real
    one — `pytest_sessionfinish` mutes it below to stop pytest printing the
    same block a second time, higher up."""
    if report.failed and not getattr(report, "wasxfail", False):
        where = report.nodeid if report.when == "call" else f"{report.nodeid} ({report.when})"
        _failures.append((where, report.longreprtext.rstrip()))
    elif report.skipped and isinstance(report.longrepr, tuple):
        # (path, lineno, reason) — worth surfacing, since the usual reason for a
        # skip here is that Postgres is not running.
        _skip_reasons[report.longrepr[2].removeprefix("Skipped: ")] += 1


def pytest_sessionfinish(session, exitstatus):
    # Runs before the terminal reporter writes its own summary, so this is what
    # suppresses its FAILURES section. The text above is already captured.
    session.config.option.tbstyle = "no"


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    tr = terminalreporter
    # The one-line FAILED/ERROR list pytest writes after this hook would repeat
    # what the failures section below already says, at more length.
    tr.reportchars = ""

    tally: dict[str, Counter] = {}
    for outcome in OUTCOMES:
        for report in tr.stats.get(outcome, []):
            nodeid = getattr(report, "nodeid", None)
            if nodeid:
                tally.setdefault(_group_of(nodeid), Counter())[outcome] += 1
    if not tally:
        return

    totals: Counter = Counter()
    for counts in tally.values():
        totals.update(counts)
    broken = totals["failed"] + totals["error"]

    width = max(len(name) for name in tally)
    tr.write_sep("=", "test summary", bold=True)
    for name in sorted(tally):
        counts = tally[name]
        hurt = counts["failed"] + counts["error"]
        tr.write(f"  {name.ljust(width)}   ")
        tr.write_line(_describe(counts), red=bool(hurt), green=not hurt)

    tr.write_sep("-")
    tr.write_line(
        f"  {_describe(totals)} in {time.time() - _started_at:.2f}s",
        bold=True,
        red=bool(broken),
        green=not broken,
    )
    for reason, count in _skip_reasons.most_common():
        tr.write_line(f"  skipped ({count}): {reason}", yellow=True)

    if _failures:
        tr.write_sep("=", "failures", bold=True, red=True)
        for i, (where, text) in enumerate(_failures, 1):
            tr.write_line("")
            tr.write_line(f"{i}. {where}", bold=True, red=True)
            for line in text.splitlines():
                tr.write_line(f"   {line}")
