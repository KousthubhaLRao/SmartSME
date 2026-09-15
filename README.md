# SmartSME

An AI-assisted, event-driven business-management platform for small and medium
businesses. Shopkeepers record sales, purchases and expenses either through
normal forms or by **typing a plain-language note / snapping a photo of a bill** —
the Smart Input Engine turns that into a structured business event, shows it for
confirmation, and publishes it onto an internal event bus that updates inventory,
party balances and alerts.

**Stack:** FastAPI + SQLAlchemy + Alembic + PostgreSQL on the backend, React +
Vite + Tailwind on the frontend, talking over a cookie-authenticated JSON API.

---

## Contents

- [Quick start](#quick-start)
- [Trying it out](#trying-it-out)
- [Troubleshooting](#troubleshooting)

---

## Quick start

**Windows, from a fresh clone:**

```powershell
.\run-dev.ps1 -Setup    # once: virtualenv, dependencies, backend\.env
.\run-dev.ps1           # every time after that
```

That is the whole thing. `run-dev.ps1` starts the containers, waits for
PostgreSQL to actually accept queries, applies any pending migrations, and opens
the API and the web app in their own windows. Running it after a `git pull` picks
up new migrations automatically.

| Flag | What it adds |
|---|---|
| `-Setup` | First run on a machine: creates `backend/.venv`, installs both dependency sets, writes `backend/.env` with a generated `AUTH_SECRET`. Takes a few minutes. |
| `-WithEmail` | Turns on inbound email collection, pointed at Mailpit. |
| `-Celery` | Runs events through Redis and Celery instead of inline. Opens a worker and a beat window. |
| `-SkipDocker` | Leaves the containers alone, for when they run elsewhere. |

When it finishes you have:

| | |
|---|---|
| App | <http://localhost:5173> |
| API docs | <http://localhost:8000/docs> |
| Mail UI | <http://localhost:8025> (Mailpit) |

Two optional channels have their own walkthroughs, written to be followed from
nothing: **[Email, step by step](docs/inbound-orders.md#email-step-by-step)** (Mailpit is already
running - this is how to send an order to it and watch it arrive) and
**[Telegram, step by step](docs/inbound-orders.md#telegram-step-by-step)** (making the bot, linking
the chat). Neither needs an account or a card.

Sign in with the seeded demo account:

| | |
|---|---|
| **Email** | `demo@smartsme.app` |
| **Password** | `demo1234` |

If script execution is blocked on your machine:
`powershell -ExecutionPolicy Bypass -File .\run-dev.ps1`.

**macOS, Linux, or by hand.** There is no shell-script equivalent yet; the same
four steps are:

```bash
docker compose up -d                    # PostgreSQL, Redis, Mailpit
cd backend
python -m venv .venv && .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                    # then set AUTH_SECRET
alembic upgrade head
uvicorn app.main:app --reload           # terminal 1

cd frontend && npm install
npm run dev                             # terminal 2
```

On first boot the API seeds a demo business ("Kirana Fresh Traders") with
products, parties, sales, purchases, expenses, workflow rules and notifications,
then starts the background event worker. Set `SEED_DEMO_DATA=false` to skip it.

To reset everything: `docker compose down -v && docker compose up -d`, then
`.\run-dev.ps1` (which re-applies the migrations).

The Vite dev server proxies `/api` to `http://localhost:8000`, which keeps the
session cookie first-party in development (no CORS or SameSite juggling).

---

## Trying it out

A ten-minute pass over everything that works, in the order it makes sense.

**1. The basics.** Sign in as the demo account. Record a sale from the Sales
page, then look at Products - the stock has already moved, because the event
chain ran before the write returned. The Event bus page shows both events and
who caused them.

**2. Smart Input, in three languages.** Open Smart Input and try these four:

```
sold 5 kg rice to Anita Stores
Anita ko 5 kilo chawal becha
अनीता को 5 किलो चावल बेचा
ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ
```

All four should produce the same draft - customer **Anita Stores**, item
**Rice Bag 25kg** at its real price - because the catalogue is matched across
scripts, not just parsed. Nothing is saved until you confirm.

**3. An order by email.** Start with `.\run-dev.ps1 -WithEmail`, then from
`backend` with the venv active:

```powershell
.venv\Scripts\python -m app.cli send-test-order "Please send 12 bags rice to Anita Stores"
```

Press **Check now** on the Inbox page. The order appears as a draft with the
customer and product already matched; accept it and it becomes a real sale.
<http://localhost:8025> shows the raw mail. Full walkthrough:
[Email, step by step](docs/inbound-orders.md#email-step-by-step).

**4. Telegram** (optional). `/newbot` to @BotFather, put the token in
`backend/.env` as `TELEGRAM_BOT_TOKEN`, restart, then
`.venv\Scripts\python -m app.cli check-telegram` prints the bot link and the
exact `/link` line to send it. Full walkthrough:
[Telegram, step by step](docs/inbound-orders.md#telegram-step-by-step).

**5. Roles.** Team -> Invite someone -> copy the join link, open it in a private
window, and set a password. That employee can record sales but will not see
Workflow or Team, and cannot delete anything.

**6. The tests.** `cd backend; .venv\Scripts\python -m pytest -q` - 364 of
them, about ten seconds. Accuracy is measured separately and on purpose:
[backend/eval](backend/eval/README.md).

**7. Under load** (optional). `python -m loadtest.seed` then the Locust command
in [Load testing](docs/performance.md#load-testing).

---

## Documentation

This page covers getting SmartSME running. Everything else lives in
[`docs/`](docs/), one page per subject:

| Page | What is in it |
|---|---|
| **[Setup and configuration](docs/setup.md)** | Installing from a clean clone, every environment variable, and where API keys go. |
| **[Architecture and layout](docs/architecture.md)** | How the pieces fit together, what lives where, and the database schema. |
| **[The event bus and how work gets dispatched](docs/events.md)** | The transactional outbox, the workflow rule engine, and inline vs Celery. |
| **[Inbound orders: email and Telegram](docs/inbound-orders.md)** | Letting customers send orders in, with step-by-step walkthroughs for both channels. |
| **[Smart Input: reading notes and photographs](docs/smart-input.md)** | The NLP engine, three scripts, catalogue matching, and the two OCR engines. |
| **[Feature reference](docs/features.md)** | What each page does: sales, purchases, stock, parties, reports and alerts. |
| **[Authentication, roles and permissions](docs/auth.md)** | Sessions, the four roles, how RBAC is enforced, and sign-in throttling. |
| **[Performance and load testing](docs/performance.md)** | Indexes, pagination, pool sizing, and driving the whole app with Locust. |
| **[The test suite](docs/testing.md)** | What is covered, how to run it, and how to add to it. |
| **[Accuracy evaluation](docs/evaluation.md)** | Measured precision/recall/F1 per engine, and what the numbers do not prove. |
| **[Deployment](docs/deployment.md)** | Taking it beyond a laptop. |
| **[HTTP API](docs/api.md)** | Every endpoint, and the conventions they share. |
| **[Design system](docs/design.md)** | Colour, type, spacing and the component vocabulary. |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused` on startup | Postgres is not running: `docker compose up -d` |
| `relation "businesses" does not exist` | Run `alembic upgrade head` |
| OCR says it needs a vision provider | No key that can read images. Set `GOOGLE_API_KEY` (free) or `OCR_SPACE_API_KEY` (free) |
| Every AI call returns 404 | The pinned model name retired. Check what the key can reach and update `GEMINI_MODEL` |
| Parsing feels "dumb" (no dates/discounts) | No API key set, so the regex fallback is running. Settings shows the active engine |
| 401 on every request from the SPA | Cookie blocked: use the Vite proxy in dev, or set `CORS_ORIGINS` + `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` in prod |
| Demo data looks wrong | `docker compose down -v && docker compose up -d && alembic upgrade head` |
| Invoice prints with the dark theme | Print from the invoice page; the handler swaps to light automatically |

---
