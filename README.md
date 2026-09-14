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
- [Setting up on a new machine](#setting-up-on-a-new-machine)
- [Environment variables](#environment-variables)
- [Repository layout](#repository-layout)
- [Feature tour](#feature-tour)
- [Architecture](#architecture)
- [Database schema](#database-schema)
- [Event bus & workflow engine](#event-bus--workflow-engine)
- [Performance](#performance)
- [Load testing](#load-testing)
- [Event dispatch: inline or Celery](#event-dispatch-inline-or-celery)
- [Inbound orders (email and Telegram)](#inbound-orders-email-and-telegram)
- [Smart Input Engine (NLP + OCR)](#smart-input-engine-nlp--ocr)
- [Alert log](#alert-log)
- [Reports](#reports)
- [Auth](#auth)
- [API reference](#api-reference)
- [Design system](#design-system)
- [Tests](#tests)
- [Deployment](#deployment)
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

**2. Smart Input, in three languages.** Open Smart Input and try:

```
sold 5 kg rice to Anita Stores
Anita ko 5 kilo chawal becha
ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ
```

Each should produce the same draft. Nothing is saved until you confirm.

**3. An order by email.** Start with `.\run-dev.ps1 -WithEmail`, open the Inbox
page, and copy the address from **Set up channels**. Send something to it:

```powershell
# from the repo root, with the venv active
python -c @"
import smtplib
from email.message import EmailMessage
m = EmailMessage()
m['From'] = 'Anita <anita@example.com>'
m['To']   = 'orders+PASTE_YOUR_TOKEN@smartsme.local'
m['Subject'] = 'Order'
m.set_content('Please send 12 bags rice to Anita Stores')
smtplib.SMTP('localhost', 1025).send_message(m)
"@
```

Press **Check now** on the Inbox page. The order appears as a draft; accept it
and it becomes a real sale. <http://localhost:8025> shows the raw mail.

**4. Telegram** (optional). Get a token from @BotFather, put it in
`backend/.env` as `TELEGRAM_BOT_TOKEN`, restart, and message your bot
`/link <your-inbox-token>`. Anything that chat sends afterwards lands in the
Inbox.

**5. Roles.** Team -> Invite someone -> copy the join link, open it in a private
window, and set a password. That employee can record sales but will not see
Workflow or Team, and cannot delete anything.

**6. The tests.** `cd backend; .venv\Scripts\python -m pytest -q` - 260 of
them, about ten seconds.

**7. Under load** (optional). `python -m loadtest.seed` then the Locust command
in [Load testing](#load-testing).

---

## Setting up on a new machine

What to do after cloning or pulling on a machine that has never run SmartSME.

**On Windows, `.\run-dev.ps1 -Setup` does all of this for you** - the steps
below are what it runs, and what to do by hand on macOS or Linux. Nothing here
is optional: the repo deliberately carries no secrets, no virtualenv and no
`node_modules`, so they have to be built locally.

### 1. Install the prerequisites

| Tool | Version | Check it with |
|---|---|---|
| Git | any | `git --version` |
| Python | 3.10 or newer | `python --version` |
| Node.js | 18 or newer | `node -v` |
| Docker Desktop | any, and **running** | `docker ps` |

On Windows, install Python from python.org with **"Add python.exe to PATH"**
ticked, and start Docker Desktop before going further — `docker ps` has to answer
with a table, not an error.

### 2. Get the code

```bash
git clone <repo-url> SmartSME
cd SmartSME
```

### 3. Start PostgreSQL

```bash
docker compose up -d       # Postgres 16 (:5432), Redis 7 (:6379), Mailpit (:1025/:8025/:1110)
docker ps                  # expect smartsme-db-1, smartsme-redis-1 and smartsme-mailpit-1
```

There is no embedded-database fallback: the API exits on startup if it cannot
reach Postgres. Nothing needs to be installed on the host — the database lives
inside the container, and `psql` can be reached with
`docker exec -it smartsme-db-1 psql -U smartsme -d smartsme`.

### 4. Set up the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate              # Windows PowerShell
# source .venv/bin/activate         # macOS / Linux
pip install -r requirements.txt
```

Then create the config, **which the pull does not bring** — `backend/.env` is
git-ignored so that nobody's keys travel through the repo. Every machine makes
its own from the template:

```bash
copy .env.example .env              # Windows;  cp .env.example .env elsewhere
```

Open `backend/.env` and set `AUTH_SECRET` to a long random string. Generate one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

The defaults for everything else already match the Docker database and the Vite
dev server, so `AUTH_SECRET` is the only line that must change. An AI key is
optional — see [step 7](#7-optional-turn-on-the-ai-features).

Create the schema:

```bash
alembic upgrade head
```

### 5. Set up the frontend

```bash
cd ../frontend
npm install
```

### 6. Run it

On Windows, from the repo root - this also starts the containers and applies
migrations, so it is the only command you need:

```powershell
.\run-dev.ps1
```

Or start the two servers by hand, in two terminals:

```bash
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload
cd frontend && npm run dev
```

Open <http://localhost:5173> and sign in as `demo@smartsme.app` / `demo1234`. The
first boot seeds that demo business automatically.

To confirm the whole stack is wired up, run the tests — 78 should pass:

```bash
cd backend
.venv\Scripts\python -m pytest -q
```

### 7. Optional: turn on the AI features

Without a key the app still runs: Smart Input falls back to a built-in regex
parser and photo OCR is disabled with a message explaining why. To enable both,
put one key in `backend/.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GROQ_API_KEY` or `GOOGLE_API_KEY`) and restart the API. The Settings page shows
which provider is live and whether it can read images.

### What the pull does not include

| Path | Why | How to get it |
|---|---|---|
| `backend/.env` | holds secrets | copy `backend/.env.example`, set `AUTH_SECRET` |
| `backend/.venv/` | machine-specific | `python -m venv .venv` + `pip install -r requirements.txt` |
| `frontend/node_modules/` | machine-specific | `npm install` |
| the database | lives in a Docker volume | `docker compose up -d` + `alembic upgrade head` |
| `.env.local`, `.neon` | Neon deployment credentials | not needed to run locally |

### If something goes wrong on the first run

| Symptom | Cause | Fix |
|---|---|---|
| `WinError 10013` on uvicorn, or `address already in use` | port 8000 is taken | `netstat -ano \| findstr :8000`, then stop that process |
| `Port 5173 is in use, trying another one` | another Vite is running | harmless — the proxy still targets :8000 — or stop the other one |
| Postgres container will not start, port 5432 in use | a native PostgreSQL is installed on the host | stop that service, or change the published port in `docker-compose.yml` |
| API exits with a connection error on startup | the container is not running | `docker compose up -d` |
| `alembic` / `uvicorn` "not recognised" | the virtualenv is not active | activate it, or call `.venv\Scripts\python -m uvicorn ...` |
| `.\run-dev.ps1` is blocked | PowerShell execution policy | `powershell -ExecutionPolicy Bypass -File .\run-dev.ps1` |
| `does not provide an export named …` in the browser | Vite cached a module that has since changed | stop the dev server and `npm run dev` again |
| relation "businesses" does not exist | migrations never ran | `alembic upgrade head` |

---

## Environment variables

Backend config lives in `backend/.env` (see `backend/.env.example`).

```bash
# ---- Database (required) ----
DATABASE_URL="postgresql+psycopg://smartsme:smartsme@localhost:5432/smartsme"

# ---- Auth ----
# 32+ chars. Generate one: python -c "import secrets; print(secrets.token_hex(32))"
AUTH_SECRET="..."
COOKIE_SECURE=false          # true when serving the API over HTTPS
COOKIE_SAMESITE=lax          # "none" + secure when API and SPA are on different sites

# ---- Frontend ----
CORS_ORIGINS="http://localhost:5173"

# ---- Behaviour ----
SEED_DEMO_DATA=true
DISABLE_WORKER=false         # true on serverless: writes drain the queue inline
WORKER_POLL_SECONDS=1.0

# ---- AI provider (optional; enables smarter NLP and all OCR) ----
# Set ONE key. If several are set the first below wins, unless AI_PROVIDER
# forces a choice (anthropic | openai | groq | google).
ANTHROPIC_API_KEY=""
ANTHROPIC_MODEL="claude-sonnet-5"

OPENAI_API_KEY=""
OPENAI_BASE_URL="https://api.openai.com/v1"   # also OpenRouter, Together, Ollama
OPENAI_MODEL="gpt-4o-mini"

GROQ_API_KEY=""
GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"   # OCR needs a vision model

GOOGLE_API_KEY=""
GEMINI_MODEL="gemini-2.0-flash"
```

**Without an API key** the app still runs: text input falls back to a built-in
regex parser, and image OCR is disabled with an explanatory message. The Settings
page shows which provider is active and whether it can read images.

---

## Repository layout

```
SmartSME/
├── docker-compose.yml          PostgreSQL 16 + Redis 7 + Mailpit
├── run-dev.ps1                 starts both dev servers (Windows)
├── backend/
│   ├── alembic/                migrations (versions/0001_initial_schema.py)
│   ├── alembic.ini
│   ├── pyproject.toml          ruff (lint + format) and pytest config
│   ├── requirements.txt
│   ├── loadtest/               locustfile + seeding script
│   ├── tests/                  pytest
│   │   ├── conftest.py         scratch test database + client fixtures
│   │   ├── test_domain.py      pure domain logic, no database
│   │   ├── test_api_smoke.py   every endpoint, end to end
│   │   ├── test_rbac.py        roles, invites and sign-in throttling
│   │   ├── test_pagination.py  paging envelopes and whole-set totals
│   │   ├── test_event_actor.py who caused each event
│   │   ├── test_dispatch.py    inline vs Celery dispatch
│   │   ├── test_multilingual.py Hindi and Kannada input
│   │   ├── test_ai_mocked.py   the AI path with the model faked
│   │   ├── test_alerts.py      the alert log
│   │   ├── test_inbound.py     email and Telegram, end to end
│   │   └── test_review_regressions.py  bugs a review caught
│   └── app/
│       ├── main.py             FastAPI app, CORS, lifespan (seed + worker)
│       │
│       ├── core/               cross-cutting infrastructure, no business rules
│       │   ├── config.py       settings from the environment
│       │   ├── db.py           engine + session factory + get_db
│       │   ├── deps.py         require_user, per-request session
│       │   ├── security.py     PBKDF2 hashing + JWT session cookie
│       │   └── utils.py        money, rounding, date parsing
│       │
│       ├── models/             SQLAlchemy models (14 tables)
│       │   ├── base.py         Base + column helpers + document mixins
│       │   ├── business.py     Business · User
│       │   ├── party.py        Party
│       │   ├── product.py      Product · StockMovement
│       │   ├── sale.py         Sale · SaleItem
│       │   ├── purchase.py     Purchase · PurchaseItem
│       │   ├── expense.py      Expense
│       │   ├── event.py        Event (the outbox table)
│       │   ├── workflow.py     WorkflowRule · WorkflowExecution
│       │   └── notification.py Notification
│       │
│       ├── schemas/            Pydantic request payloads (the wire contract)
│       │   ├── common.py       LineInput · DocumentInput · PaymentInput · …
│       │   ├── sale.py         SaleInput · SaleTotals
│       │   ├── purchase.py     PurchaseInput · PurchaseTotals
│       │   ├── catalog.py      ProductInput · PartyInput · ExpenseInput · …
│       │   ├── auth.py         SignInInput · SignUpInput
│       │   ├── ops.py          RuleInput · SettingsInput
│       │   └── smart_input.py  ParseTextInput
│       │
│       ├── domain/             business rules: sales · purchases · payments ·
│       │                       catalog · line_items
│       ├── routers/            auth · sales · purchases · catalog · input ·
│       │                       reports · ops
│       ├── ai/                 client.py · nlp.py · ocr.py · lang.py
│       │
│       ├── inbound/            email + Telegram -> the review queue
│       ├── celery_app.py       Celery application (Redis broker)
│       ├── tasks.py            process_event, sweep_outbox
│       ├── pagination.py       ?page= / ?pageSize= helpers
│       ├── serializers.py      the JSON shapes the SPA consumes
│       ├── events.py           the outbox (publish)
│       ├── workflow.py         core effects + WHEN/THEN rule engine
│       ├── worker.py           claim / retry / dead-letter loop
│       ├── analytics.py        dashboard + revenue series
│       ├── reports.py          report builder, PDF (reportlab) and CSV
│       ├── smart_input.py      grounding: party/product matching, drafts
│       └── seed.py             demo tenant
└── frontend/
    ├── vite.config.ts          React plugin, Tailwind plugin, /api proxy
    ├── .prettierrc.json        formatting rules
    └── src/
        ├── App.tsx             routes + session guard
        ├── index.css           design tokens (light/dark) + print rules
        ├── lib/                api.ts (client + hooks) · utils.ts · countries.ts
        ├── components/         AppShell, AuthLayout, RevenueChart,
        │                       LineItemsEditor, ui/*
        └── pages/              Dashboard, SmartInput, Sales, SaleInvoice,
                                Purchases, Products, Parties, Expenses, Reports,
                                Workflow, Events, Notifications, Settings, auth
```

**Layer rules.** `core` never imports `models`, `domain` or `routers`, so it can be
imported from anywhere without a cycle — which is why the declarative `Base` lives in
`models/base.py` rather than in `core/db.py`. `schemas` holds one payload per
operation, shared by the router that receives it and the domain function that
consumes it; `schemas.common.BusinessDate` accepts either a `yyyy-mm-dd` string from
HTTP or an already-parsed `datetime` from an internal caller, so neither layer needs
its own copy of the payload. Responses are built by `serializers.py`, not by schemas.

---

## Feature tour

### Dashboard
Six KPI cards (sales, purchases, expenses, inventory value, receivable, payable),
each clicking through to its page. Revenue chart, a heuristic **business-health
score** (inventory / revenue / expenses / cash flow), Recent Sales and Recent
Purchases side by side, and a low-stock "Needs attention" panel.

### Smart Input (`/input`)
Two modes: **natural language** (type `Sold 10 rice bags to Kumar Traders`) and
**image / OCR** (upload an invoice, order slip or WhatsApp screenshot). Either way
you land on a **confirmation screen** with the extracted party, line items,
discount and date, all editable, before anything is written. Typed text and the
parsed draft both survive navigating away and back, until the draft is published.

### Sales & Purchases
Full list with source badge (Form / AI·Text / AI·OCR) and payment status. Click
**any row** for a detail modal with line items, totals, and a click-to-edit
transaction date. Inline "Record payment" and "Cancel"; cancelling reverses
inventory and the party balance. Sales also have a printable invoice at
`/sales/:id`.

Both support **discounts** (flat amount or percentage) applied to the subtotal
before tax, with a live preview while you type and a hard block when the discount
exceeds the document value.

### Transaction dates
Every sale and purchase carries a business `date` separate from `created_at`. It
defaults to today, can be set at creation, and corrected afterwards from the
detail modal, for entries logged late. Lists, charts, analytics and reports all
key off this date.

### Parties (`/parties`)
Customers and suppliers with running balances. Each party row expands to show the
individual unpaid invoices/bills behind its balance, with **"Pay all"** per party
and **"Mark all as paid"** for all receivables or all payables. Phone numbers use
a country-code dropdown (202 countries).

### Products, Expenses, Notifications
Inventory with stock, HSN/SKU, low-stock thresholds and a stock-movement history;
manual stock adjustments that can never drive stock negative; categorised expenses
with their own dates; an alerts inbox fed by the workflow engine.

### Alert log

Alerts are raised by workflow rules and listed on the Notifications page. Each
one records **which rule fired, on which event, and therefore who caused it**
(`notifications.event_id` / `rule_id`, migration `0005`) — the difference
between a message and something you can audit.

The list filters by severity and by unread, and an alert can be marked unread
again, dismissed, or cleared in bulk once dealt with. Both source columns are
nullable and `SET NULL` on delete: an alert outlives the rule that raised it
rather than vanishing with it, and shows no source instead.

The notify action dedupes against *unread* alerts of the same title, so a noisy
rule cannot bury the one that matters.

---

## Reports (`/reports`)
KPI cards, a **revenue chart** with a Y axis, hover tooltips showing exact values,
and a range selector (last week / month / 3 / 6 months / year) that buckets daily,
weekly or monthly as appropriate. Top products, top customers, expenses by
category, cash-flow summary, and **downloadable reports** (see below).

### Workflow (`/workflow`) and Event bus (`/events`)
Toggle built-in rules or add your own `WHEN <event> [condition] THEN <action>`
rule. The event bus page shows events flowing `pending → done`, with retry,
dead-letter, replay and a manual drain, and polls while open.

---

## Architecture

One FastAPI process, one Postgres database, one React SPA, and an event bus in
between. Nothing is a microservice; the pieces below are modules, not servers.

```
   browser (React SPA, Vite)
        |  cookie-authenticated JSON over /api/*
        v
   FastAPI  --- routers ---> domain layer ---> SQLAlchemy ---> PostgreSQL
        |                        |                                 ^
        |                        +-- publish(event) --------------+ |
        |                                  (same transaction)       |
        |                                                           |
   inbound channels                    event bus (outbox table)     |
   email / Telegram  --> review queue        |                      |
                                             v                      |
                                   workflow engine ---> stock, balances,
                                   (rules: WHEN/THEN)    alerts, notifications
```

**Requests** go router -> domain -> database. Routers do HTTP: parsing,
permissions, serialization. The domain layer holds the business rules and knows
nothing about HTTP. Responses are built by `serializers.py`, never by the ORM
models directly.

**Writes publish events** into an outbox table *in the same transaction* as the
data they describe. That is the spine of the whole design: a sale and the
"a sale happened" record either both exist or neither does. The workflow engine
then applies the consequences - moving stock, updating a party balance, raising
a low-stock alert - by reading that outbox. Effects are never written inline by
the code that caused them.

**Dispatch** decides *when* those consequences land: inline (before the write
returns, the default) or through Redis and Celery workers. Either way the outbox
is the source of truth. See [Event dispatch](#event-dispatch-inline-or-celery).

**Every row is scoped to a business.** Multi-tenancy is a `business_id` column
and a permission check on every route, not separate databases. Platform roles
reach across tenants by naming one explicitly.

**The Smart Input engine** turns free text into a draft. It is reached three
ways - the in-app window, an emailed order, a Telegram message - and all three
produce the same draft object and the same confirm-before-recording step.


```
React SPA (Vite)                     FastAPI
────────────────                     ───────
pages/  ──fetch('/api/…')──►  routers/  ──►  domain/   ┐ business rows
  (session cookie)                          events.py  ┘ + event, ONE transaction
                                                 │
                                          events table (outbox)
                                                 │
                                          worker.py  claim → run rules → retry → dead-letter
                                                 │
                                    inventory · party balances · notifications

Smart Input ──► ai/ (provider-agnostic NLP + OCR)
                  │
            smart_input.py  grounds the result against the tenant's own data
                  │
            human confirmation ──► the same domain layer
```

**Why the event bus is a table.** It is the **transactional outbox pattern**: the
business rows and the event commit together, so an event can never be lost for a
write that succeeded, nor emitted for one that rolled back. The worker claims rows
atomically (`status='pending' → 'processing'`), runs each event's rules inside a
single transaction, retries with a bounded counter and dead-letters after 5
attempts. That gives the same guarantees a broker would, without a second piece
of infrastructure. Tunables live in `app/worker.py`: `BATCH = 20`,
`MAX_RETRIES = 5`, poll interval from `WORKER_POLL_SECONDS`.

Because every event handler is one transaction, an automatic retry is safe: a
failed attempt leaves nothing half-applied. Manual replays are additionally
guarded by a check for existing stock movements, so re-running a sale cannot
double-apply inventory.

**Splitting the frontend from the API** makes this a genuinely service-oriented
deployment: the SPA is static files, the API is a stateless process, and the
worker can run in-process or be split out. The AI layer is the natural next
service to extract if you ever want to.

---

## Database schema

SQLAlchemy models in `backend/app/models/`, migrations in `backend/alembic/`.

| Table | Purpose |
|---|---|
| `businesses` | Tenant root: name, GSTIN/PAN, address, currency, `tax_rate`, `invoice_prefix` |
| `users` | Email + PBKDF2 password hash, role, belongs to a business |
| `parties` | Customers and suppliers, with a running `balance` |
| `products` | Stock, unit, HSN/SKU, purchase/selling price, low-stock threshold |
| `stock_movements` | Append-only inventory ledger (`delta`, reason, ref) |
| `sales` / `sale_items` | Invoices: subtotal, discount (type/value/amount), tax, total, paid, status, `date` |
| `purchases` / `purchase_items` | Supplier bills, same shape as sales |
| `expenses` | Category, description, amount, `date`, workflow `flagged` marker |
| `events` | The outbox: type, JSONB payload, status, retry count, error |
| `workflow_rules` / `workflow_executions` | Rule definitions and their audit trail |
| `notifications` | Alerts surfaced in the bell menu |

Positive `parties.balance` means *they owe us* (customer) or *we owe them*
(supplier). Money is `double precision` and every amount passes through `round2`.
Timestamps are naive and treated as local time, so day/month boundaries in reports
match the user's calendar.

Indexes cover the three hot paths: pending-event polling, per-event rule lookup,
and the unread-notification badge.

### Working with migrations

```bash
cd backend
alembic upgrade head                              # apply
alembic downgrade -1                              # roll back one
alembic revision --autogenerate -m "add x"        # after editing app/models/
alembic upgrade head --sql                        # render DDL without a database
```

`alembic/env.py` reads `DATABASE_URL` from the app settings, so migrations and the
app can never drift onto different databases.

---

## Performance

### Indexes

Postgres does not index a foreign key for you, so until migration `0003` every
query scoped to one business — which is every query in the app — was a
sequential scan over the whole table. Measured on 200,000 sales across 50
businesses, for the query behind the sales list:

| | Plan | Time | Buffers read |
|---|---|---|---|
| Without the index | Parallel Seq Scan + sort, 2 extra workers | 10.50 ms | 4,517 |
| With it | Index Scan | 0.067 ms | 53 |

The indexes are listed in `alembic/versions/0003_tenant_indexes.py`. Each one
matches a real access path: the leading column is the tenant filter, the
trailing one the sort or join, so the planner satisfies both from the index —
`(business_id, date DESC)` for the document lists, `(business_id, name)` for the
catalogue, `(sale_id)` for line items.

### Pagination

Every list endpoint takes `?page=` and `?pageSize=` (default 50, maximum 200)
and returns the rows alongside an envelope:

```json
{ "rows": [...], "page": { "page": 1, "pageSize": 50, "total": 214, "pages": 5, "hasMore": true } }
```

`app/pagination.py` holds the shared helpers. Offset rather than cursor,
deliberately: the SPA shows numbered pages over data sorted by a business date,
and a cursor would buy accuracy under concurrent inserts that nobody here would
notice.

**Totals are aggregated in SQL, not summed from the returned rows.** That is the
part worth remembering — the rows are now one page of the set, so summing them
would make a dashboard quietly report one page's worth of money. `tests/test_pagination.py`
asserts that asking for `pageSize=1` returns identical statistics to asking for
all of them.

The same change fixed the parties endpoint, which used to load every sale and
every purchase in the business into memory to work out who owed what; it now
asks only for the unsettled documents belonging to the parties on the current
page.

Still unbounded, and fine for now: the product and party pickers inside the new
sale and purchase forms, which fetch the whole catalogue to populate a dropdown.

---

## Load testing

```bash
cd backend
python -m loadtest.seed                 # a business with 4000 sales of history
uvicorn app.main:app --workers 4        # see "Workers", below
locust -f loadtest/locustfile.py --host http://localhost:8000 \
    --headless -u 200 -r 8 -t 60s
```

`loadtest/locustfile.py` models a shop floor rather than a benchmark: roughly
eight reads per write, weighted towards the dashboard and the document lists,
with sales, expenses and Smart Input parses underneath. Each simulated user signs
in once and keeps its cookie - re-authenticating every request would measure
PBKDF2 rather than the app.

`python -m loadtest.seed --reset` removes the load-test business afterwards.

### What the first run found

200 concurrent users against 4000 sales, on a 16-core laptop:

| | requests | failures | throughput | median | p95 |
|---|---|---|---|---|---|
| Baseline | 129 | 19.4% | 3.5 req/s | 2,200 ms | 33,000 ms |
| Bigger connection pool | 430 | 19.3% | 9.8 req/s | 6,500 ms | 31,000 ms |
| + 4 uvicorn workers | 994 | 5.4% | 16.8 req/s | 3,500 ms | 19,000 ms |
| **+ SQL aggregates** | **6,301** | **0%** | **106.3 req/s** | **33 ms** | **150 ms** |

Three separate ceilings, each hiding the next:

**1. The connection pool.** SQLAlchemy defaults to 5 connections plus 10
overflow. Fifteen is then the hard limit on concurrent requests, because each one
holds its connection for its whole life - the 33-second p95 was exactly the
30-second pool timeout, followed by a 500. Now configurable (`DB_POOL_SIZE`,
`DB_MAX_OVERFLOW`) and defaulting to 20 + 40, with a 10-second timeout so a
starved request fails fast instead of hanging. The sync endpoint thread pool is
raised to match, since one request occupies one thread *and* one connection.

**2. One process is one core.** Sign-in is PBKDF2 at 100k iterations - tens of
milliseconds of pure CPU, deliberately - and Python's GIL means a single worker
serialises all of it. Run `uvicorn --workers N` in anything but development.

**3. The dashboard was doing 1.4 seconds of Python per request.** `load_overview`
loaded every sale, purchase, expense and line item into memory and summed them
there. Rewritten as SQL aggregates:

| Endpoint | Before | After |
|---|---|---|
| `/api/dashboard` | 1.40 s | 0.24 s |
| `/api/reports/overview` | 1.64 s | 0.23 s |
| `/api/reports/revenue` | 0.99 s | 0.22 s |

Identical output - the totals, health scores and breakdowns were diffed against
the previous implementation on two tenants before and after.

### Workers and pool sizing

`(DB_POOL_SIZE + DB_MAX_OVERFLOW) x workers` must stay under Postgres's
`max_connections`, which defaults to 100. For four workers:

```bash
DB_POOL_SIZE=8 DB_MAX_OVERFLOW=12 SERVER_THREADS=20 uvicorn app.main:app --workers 4
```

---

## Event bus & workflow engine

### Who caused what

Every event records the user behind it (`events.user_id`, migration `0004`), and
the Event bus page shows it as a **By** column. That is what makes the outbox an
audit trail rather than a log — it only became meaningful once a business could
have more than one account.

The actor is passed explicitly, the same way `business_id` already is, rather
than read from a context variable: the router hands `ctx.user.id` to the domain
function, which hands it to `publish()`.

The case worth knowing about is the **chained** event. A sale raises
`SALE_CREATED`; processing that raises `STOCK_UPDATED`, in the worker, with no
HTTP request anywhere near it. Those inherit the parent event's author, so the
whole chain a single click set off is attributed to the person who clicked.

The column is nullable and the foreign key is `ON DELETE SET NULL`: events from
the seed, from a cron drain, or from someone since removed from the team keep
their place in the history with no author (shown as "System") rather than
vanishing with them.


Event types: `SALE_CREATED`, `PURCHASE_CREATED`, `STOCK_UPDATED`,
`EXPENSE_ADDED`, `PAYMENT_RECEIVED`, `ORDER_CREATED`.

`publish()` takes the **same session** as the business write:

```python
sale = Sale(...)
db.add(sale)
db.flush()
db.add_all(items)
publish(db, business_id, "SALE_CREATED", {"saleId": str(sale.id)})
db.commit()          # rows + event together
drain_queue()        # apply the chain now, so the response is already correct
```

Built-in rules seeded per business:

| Rule | When | Then |
|---|---|---|
| Update inventory on sale | `SALE_CREATED` | `update_inventory` |
| Low-stock restock alert | `STOCK_UPDATED` | `restock_alert` |
| Flag high-value expense | `EXPENSE_ADDED` (amount > 10000) | `flag_expense` |
| Unpaid sale reminder | `SALE_CREATED` (paymentStatus = unpaid) | `notify` |

Inventory and balance updates are **always-on core effects**, not rule-gated, so
the ledger stays consistent even if a rule is disabled. Every rule evaluation is
recorded in `workflow_executions` and shown on `/workflow`.

---

## Event dispatch: inline or Celery

The outbox in Postgres is the source of truth in both modes. What changes is
*who* applies the events, and *when*.

```
write + event  --commit-->  Postgres (source of truth)
                                 |
   inline mode ..................+ applied in the request, before it returns
                                 |
   celery mode ..................+-- enqueue --> Redis --> worker applies it
                                 |
                                 +-- sweep -------------> worker applies it
                                     (anything the enqueue missed)
```

### inline (the default)

`drain_queue()` follows the whole chain inside the request: a sale emits
`SALE_CREATED`, which moves stock, which may raise a low-stock alert — and all
of it lands before the client sees its `201`. The SPA depends on this: it
reloads a page after a write and expects the new stock to be there.

### celery

`EVENT_DISPATCH=celery` makes the same call hand the events to Redis instead and
return. A Celery worker applies them a moment later. Writes get much cheaper,
and workers scale out independently of the API.

**The trade you are making:** the write returns before its effects exist. Record
a sale and read stock back in the same breath and you may see the old number for
a few milliseconds. That is why inline is the default and celery is opt-in.

```bash
docker compose up -d                  # Postgres + Redis
# Windows
.\run-dev.ps1 -Celery                 # API, SPA, worker and beat, all in celery mode
# or by hand
EVENT_DISPATCH=celery uvicorn app.main:app --reload
celery -A app.celery_app worker --loglevel=info --pool=solo -Q smartsme   # Windows
celery -A app.celery_app worker --loglevel=info -c 8 -Q smartsme          # Linux
celery -A app.celery_app beat --loglevel=info
```

`--pool=solo` is required on Windows; the default prefork pool does not work
there. On Linux use `-c N` for N concurrent workers.

### Why the outbox stays

Redis is the broker and nothing more. The event row is committed in the same
transaction as the business data, so:

- an event can never exist for a write that rolled back, and
- a write can never be silently missed, even if Redis is down at that moment.

If the enqueue fails, the request still succeeds — the row is already committed
as `pending`, and **the beat sweep re-delivers it** once the broker is back. An
event that has sat pending for `CELERY_STRANDED_SECONDS` is considered stranded
and re-queued; fresher ones are left alone, because their enqueue may still be
in flight.

The sweep also frees events a worker died holding, which would otherwise sit in
`processing` forever - the sweep reads `pending`, and a redelivered task loses
the claim race. What counts is the age of the **claim** (`events.claimed_at`,
migration `0007`), not the age of the event. Judging by `created_at` is wrong in
exactly the situation the sweep exists for: after an outage the whole backlog is
old, so every row a live worker had just picked up looks abandoned, and freeing
it hands one event to two workers at once.

### Delivery is at-least-once, application is exactly-once

Redis can hand the same task to two workers. `claim()` flips the row from
`pending` to `processing` in a single atomic `UPDATE ... WHERE status='pending'`,
so the loser of that race does nothing and returns `"skipped"`. Retries stay
with the outbox (`retry_count`, dead-lettering at five) rather than being
duplicated by Celery's own retry machinery.

### Chained events

An event applied by a worker can raise more events, inside the worker's own
transaction, where no request is around to enqueue them. The task hands those
on itself as soon as its transaction commits — so the whole chain a single click
set off completes in milliseconds rather than waiting for the next sweep.

---

## Inbound orders (email and Telegram)

Smart Input is the window inside the app. The same engine also reads orders that
arrive from outside, so a customer can email or message an order and it reaches
the same confirm screen.

**Nothing external ever writes to the books.** An inbound message becomes a
*draft* in a review queue on the Inbox page; a signed-in user with `txn:write`
accepts it, and only then is a sale recorded. Accepting is the only path that
writes, and the draft is editable first, because the parser is a suggestion.

Reading the queue needs `data:read`, so an admin can see what arrived. Deciding
what becomes of a message - accepting, dismissing, or fetching more - needs
`txn:write`, which an admin does not hold: dismissing a customer's order is a
decision about a business's data, not part of configuring it. Deleting from the
queue needs `data:manage`, like any other destruction.

### Email

Routing is by plus-address: each business has an `inbox_token`, and mail sent to
`orders+<token>@your-domain` lands in that business's queue. Mail that carries no
recognised token is dropped rather than guessed at.

Two protocols, both stdlib, no dependency added:

* **POP3** for local development, which is what Mailpit speaks. `docker compose
  up -d` gives you a working inbox with nothing to sign up for: SMTP on **:1025**,
  a web UI on **<http://localhost:8025>**, POP3 on **:1110**.
* **IMAP** for a real mailbox (Gmail, Zoho, a company server). Collected mail is
  marked read rather than deleted, so the user keeps their copy.

Try it locally:

```bash
# 1. Turn ingestion on in backend/.env
EMAIL_INGEST_ENABLED=true

# 2. Send an order to the inbox address (the token is on the Inbox page)
python - <<'PY'
import smtplib
from email.message import EmailMessage
m = EmailMessage()
m["From"] = "Anita <anita@example.com>"
m["To"] = "orders+<your-token>@smartsme.local"
m["Subject"] = "Order"
m.set_content("Please send 12 bags rice to Anita Stores")
with smtplib.SMTP("localhost", 1025) as s:
    s.send_message(m)
PY
```

Then open the Inbox page and press **Check now** (or wait for the poll).

### Telegram

Telegram is the one mainstream messenger with a genuinely free, instantly
self-issued API key - message **@BotFather**, send `/newbot`, get a token. No
card, no business verification, no approval queue. That is why it is the channel
wired up; WhatsApp Business needs Meta approval and a verified number, and Signal
has no official API.

```bash
TELEGRAM_BOT_TOKEN="123456:ABC-your-token"
```

Telegram cannot know which shop a chat belongs to, so the owner sends the bot
`/link <inbox-token>` once. That chat is bound from then on; anything else it
sends becomes a draft. A message from an unlinked chat gets a short reply
explaining how to link, and is otherwise ignored.

Long polling (`getUpdates`), not webhooks, so it works from a laptop behind NAT
with nothing to expose.

### Deduplication and scheduling

The `(business, channel, external_id)` unique constraint means a re-delivered
email or a repeated Telegram update can never be ingested twice - which matters
because the dedup key is the *message*, not the chat: two orders from one
customer are two drafts, not one. It is scoped to the business because the id
belongs to the channel rather than to us: a supplier mailing the same order to
two shops sends one `Message-ID`, and both shops need to see it.

Telegram is acknowledged by offset, advanced once per update after it has been
dealt with - late enough that a failed insert is retried rather than lost, early
enough that an update nothing can read (a photo, a sticker) does not pin the
offset and get re-read every thirty seconds for a day.

The sweep runs every `INBOUND_POLL_SECONDS` (30 by default): on its own thread in
inline mode, and as a Celery beat task in celery mode. Its own thread because it
is the slow, unreliable one - it talks to a mail server and then to an AI
provider - and a mailbox nobody can reach must not stop sales from updating
stock. `POST /api/inbox/collect` triggers it by hand, which is what the **Check
now** button does.

---

## Smart Input Engine (NLP + OCR)

`app/ai/client.py` is a **provider-agnostic** layer over httpx: Anthropic, OpenAI
(or any OpenAI-compatible endpoint), Groq and Google Gemini all implement one
`complete(prompt, system, image)` call. `get_provider()` picks the first
configured key in the order anthropic → openai → groq → google, unless
`AI_PROVIDER` forces one. Vision support is reported per model, so a text-only
Groq model correctly disables OCR instead of failing at the API.

A provider that is failing is dropped rather than retried: after three
consecutive failures it is skipped outright for two minutes and callers fall
straight through to the heuristic parser. At a sixty-second timeout each, a
queue of twenty-five mailed orders would otherwise take twenty-five minutes to
fail one at a time.

### Languages

A note can arrive in English, Hindi or Kannada, in Devanagari or Kannada script
or typed in Latin letters, and often mixes them in one sentence:

| | |
|---|---|
| English | `sold 5 kg rice to Anita Stores` |
| Hinglish | `5 kilo chawal Anita ko becha` |
| Hindi | `अनीता को 5 किलो चावल बेचा` |
| Kannada | `ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ` |
| Kanglish | `Anita ge 5 kilo akki maride` |

With an AI key the model handles the language directly, and the prompt tells it
which ones to expect. Without one, `app/ai/lang.py` rewrites the note into the
English shape the built-in parser already understands, so the fallback speaks
every language too:

```
"ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ"  ->  "to ಅನಿತಾ 5 kg ಅಕ್ಕಿ sold"
```

Two things it does beyond swapping words:

- **Native digits become numbers.** ೫ and ५ are 5; a quantity is useless
  otherwise.
- **Word order is repaired.** Hindi and Kannada mark the recipient *after* the
  name — "Anita ko", "ಅನಿತಾಗೆ" — where English puts a preposition before it.
  Kannada glues it on as a suffix, which is why the vocabulary is applied first:
  ಬಾಡಿಗೆ means "rent" and happens to end in ಗೆ ("to"), and splitting it would
  invent a customer called ಬಾಡಿ.

**Names and products are never translated.** They come out in the script they
went in, because that is how they sit in the catalogue and how the fuzzy matcher
finds them.

Hindi कल is both yesterday and tomorrow. A note about something already done
resolves to yesterday; one about something a customer wants resolves to
tomorrow.

### Text (`app/ai/nlp.py`)
1. One prompt asks the model for strict JSON: `eventType`, `party`, `product`,
   `quantity`, `amount`, `category`, `allInventory`, `discountType`,
   `discountValue`, `date`.
2. `extract_json()` pulls the first `{…}` out of the reply and `_normalize()`
   validates every field.
3. **With no key, or if the call fails**, it falls back to `heuristic_parse()`, a
   dependency-free regex parser covering the same fields.

Understood today, among others:

| You type | It extracts |
|---|---|
| `Sold 10 rice bags to Kumar Traders` | sale, qty 10, product Rice, party Kumar Traders |
| `Purchase 50 sugar packets from ABC Suppliers` | purchase (party type corrects the direction) |
| `Paid electricity bill 3200` | expense, category Utilities |
| `Sell everything to Anita Stores at a discount of 10%` | one line per in-stock product, 10% discount |
| `Sold 4 litres cooking oil to Shree on 20th August 2026` | date `2026-08-20` |

Dates accept `20th August 2026`, `20 aug`, `3 sept`, `August 20 2026`,
`20/08/2026`, `2026-08-20`, `today`, `yesterday`, `day before yesterday`. With no
date stated it defaults to today. Impossible dates (31 Feb) are rejected, and a
bare day+month rolls back a year rather than landing in the future.

### Images (`app/ai/ocr.py`)
The same provider, with the image attached, returns `party`, `docType`,
`lineItems`, `total`, `date`, `discountType`, `discountValue` — feature parity
with the text path. **OCR requires a vision-capable provider; there is no
offline fallback.**

### Grounding (`app/smart_input.py`)
Both paths then run the same matching step:

- **Party matching** — `best_match()` tries exact (normalised), substring, then
  token-subset, so "Anita", "anita stores." and "ANITA STORES" all resolve.
- **Direction correction** — a matched party's own type is authoritative, so a
  named customer forces `sale` even if the model guessed `purchase`.
- **Product matching** against the catalogue, falling back to a custom line.
- **"Entire inventory"** expands to one line per in-stock product.

Nothing is written until you confirm.

---

## Reports

`app/reports.py` builds a report for a **type** (sales, purchases, expenses, or
everything consolidated) over a **period**: today, last 7 days, this month, last
month, last 3 / 6 months, this year, last 12 months, or a custom range. It renders
server-side to **PDF** (reportlab, landscape A4, repeating table headers and page
numbers) or **CSV**, served as a normal download:

```
GET /api/reports/download?type=consolidated&preset=month&fmt=pdf
GET /api/reports/preview?type=sales&preset=last_12_months     # totals as JSON
```

Two deliberate details: cancelled documents are **listed but excluded from
totals** (the accountant-correct behaviour), and amounts print as plain grouped
numbers with the currency stated once in the header, because the PDF core fonts
have no rupee glyph.

Invoices print in **light mode regardless of the app theme**: the print handler
temporarily removes the `.dark` class and the app chrome is hidden with
`print:hidden`, so only the invoice reaches the page.

---

## Auth

Self-contained email + password, no external provider:

- **PBKDF2-HMAC-SHA256**, 100 000 iterations, stored as `pbkdf2$<salt>$<hash>`
  (`app/core/security.py`). The format is unchanged from the previous implementation,
  so user rows migrated from the old database keep working.
- **Signed JWT session cookie** (PyJWT, HS256), httpOnly, 30 days.
- Unknown ids return 404 rather than leaking existence, and sign-in gives one
  message for both a bad email and a bad password.

`AUTH_SECRET` must be 32+ characters in production.

### Roles and permissions

Four roles, defined in `app/core/roles.py`. Two are platform-level and belong to
no business; two are tenant-level and belong to exactly one.

| Role | Scope | Can |
|---|---|---|
| **Superuser** | every business | everything |
| **Admin** | every business | read anything, change a business's *configuration* — profile, tax rate, invoice prefix, workflow rules. Never its data. |
| **Business owner** | their own business | everything inside it, including the team |
| **Employee** | their own business | record sales, purchases, expenses, payments, stock adjustments and Smart Input drafts; read the catalogue, dashboard and reports |

The admin/owner line is the important one: **no permission an admin holds can
create, amend or delete a sale, purchase, expense, product or party.** An
employee is additive-only — they log what happened, and cannot cancel, delete,
back-date or settle it afterwards.

Permissions are coarse (seven of them) rather than one per endpoint: a finer
grid is more expressive and much easier to get subtly wrong.

```python
# app/core/roles.py
EMPLOYEE: frozenset({P.DATA_READ, P.TXN_WRITE})
ADMIN:    frozenset({P.DATA_READ, P.CONFIG_WRITE, P.CROSS_TENANT})
```

Routes declare what they need, so the handler stays about the handler's job:

```python
@router.delete("/products/{product_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
```

An unrecognised role resolves to *no* permissions, so a typo in the column
closes doors rather than opening them. The SPA hides what a role cannot use
(`lib/session.tsx`), but every rule is enforced again on the API — the UI gating
is only so nobody clicks a button that will 403.

**Cross-tenant access.** A superuser or admin has `business_id = NULL` and names
the business it is acting on with `?businessId=<uuid>`; the SPA keeps that
choice in `lib/api.ts` and appends it to every request. A tenant role is pinned
to its own business, and asking for another one returns 404 rather than 403 — so
the parameter cannot be used to discover other tenants.

**Platform accounts have no sign-up route.** They are created at the console:

```bash
python -m app.cli create-platform-user --role superuser --email you@example.com
python -m app.cli list-platform-users
```

### Team invitations

Sign-up creates a business and its first owner. Everyone else joins by
invitation: an owner creates one on the Team page and gets a `/join/<token>`
link, which the invitee opens to set their own name and password.

Only the SHA-256 of the token is stored, so a leaked database cannot be used to
accept an invitation. The raw token appears once, in the response that creates
it — there is no mail transport here, so the link travels however the business
already reaches its staff. Invitations last seven days, work once, and can be
revoked. A business can never lose its last owner.

### Sign-in throttling

Two independent limits, in `app/core/throttle.py`:

- **Per account** — five failures lock the address for fifteen minutes, and each
  further five doubles it, up to a day. A successful sign-in ends the streak.
- **Per IP** — twenty failures across *all* accounts in fifteen minutes. This is
  what catches password spraying, which never trips the per-account limit.

**Employees are exempt from the account lock**, by design: their accounts are a
poor target and locking one strands a shopkeeper's staff at the counter. They
are still covered by the per-IP limit.

An unknown email is throttled exactly like a real one, so the lockout response
cannot be used to tell which addresses have accounts — with one caveat worth
knowing: it does distinguish an *employee* from everything else, which is the
price of the exemption above.

State lives in Postgres (`login_attempts`) rather than in memory, so two API
processes agree and a restart does not hand an attacker a fresh budget. Moving
it to Redis later means reimplementing one function. The thresholds are settings
(`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCK_MINUTES`, `LOGIN_WINDOW_MINUTES`,
`LOGIN_MAX_IP_ATTEMPTS`).

---

## API reference

Interactive docs at **<http://localhost:8000/docs>**. Summary:

| Area | Endpoints |
|---|---|
| Meta | `GET /api/health` (public) |
| Auth | `POST /api/auth/sign-in` · `sign-up` · `sign-out` · `GET /api/auth/me` |
| Dashboard | `GET /api/dashboard` |
| Sales | `GET/POST /api/sales` · `GET /api/sales/{id}` · `POST {id}/payment` · `{id}/cancel` · `PATCH {id}/date` |
| Purchases | same shape under `/api/purchases` |
| Products | `GET/POST /api/products` · `PUT/DELETE {id}` · `POST {id}/adjust` |
| Parties | `GET/POST /api/parties` · `PUT/DELETE {id}` · `POST {id}/settle` · `POST /settle-all/{kind}` |
| Expenses | `GET/POST /api/expenses` · `DELETE {id}` |
| Smart Input | `GET /api/input/status` · `POST /parse-text` · `/parse-image` · `/publish` |
| Reports | `GET /api/reports/overview` · `/revenue` · `/preview` · `/download` |
| Workflow | `GET /api/workflow` · `POST /rules` · `PUT/DELETE /rules/{id}` · `POST /rules/{id}/toggle` |
| Events | `GET /api/events` · `POST /events/{id}/replay` · `POST /events/drain` |
| Notifications | `GET /api/notifications` · `/unread-count` · `POST {id}/read` · `/read-all` |
| Settings | `GET/PUT /api/settings` |

Requests use camelCase JSON to match the React code; the database stays
snake_case. Domain validation errors come back as `400 {"detail": "..."}`.

---

## Design system

Tailwind v4 with CSS custom properties in `frontend/src/index.css`. Light is the
default; a `.dark` class on `<html>` flips the tokens, set before paint by an
inline script to avoid a flash. No component library — `src/components/ui/*` holds
small primitives (Button, Card, Table, Modal, Input, Badge) and
`src/components/Icon.tsx` is a dependency-free stroke icon set.

**Colour.** A muted teal brand on warm-sand neutrals in light mode, and a
desaturated teal on soft charcoal in dark - calm enough to sit in front of all
day. Nothing fluorescent, and no coloured glows: the primary button carries an
ordinary elevation shadow, cards have plain surfaces, and table rows highlight
with a neutral wash rather than a tint of the brand.

The teal is readable as text (about 5.6:1 on white), so `--link` and `--primary`
can be the same colour, which the previous neon palette could not manage. Status
colours are muted to match: a warning should read as a warning, not as an
alarm.

The chart tokens are a separate palette, validated for the OKLCH lightness band,
a chroma floor, adjacent-pair separation under colour-vision deficiency, and
contrast against the chart surface. `--chart-1` is a *more saturated* teal than
the UI brand for a reason: at the brand's chroma a thin chart line falls below
the floor and reads as grey. A calm UI colour and a legible data colour are not
the same requirement.

The sign-in and sign-up pages share `src/components/AuthLayout.tsx`: a lime brand
panel beside the form. The panel keeps its colour in both themes — it *is* the
brand — while the form panel follows the app surface, and below `lg` it collapses
to a banner above the form rather than disappearing.

The sidebar is resizable by dragging the handle on its edge and collapses to an
icon-only rail when that handle is clicked; both the width and collapsed state
persist.

Data loading uses two small hooks in `src/lib/api.ts` (`useApi` for reads,
`useMutation` for writes) rather than a data-fetching library — the app is almost
entirely "load a page, mutate, reload".

---

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest -q              # 260 tests
```

```
================================ test summary =================================
  AI (mocked)        26 passed
  Alert log           9 passed
  Dispatch            8 passed
  Domain units       42 passed
  Endpoint smoke     36 passed
  Event authors       6 passed
  Inbound orders     28 passed
  Languages          46 passed
  Paging               25 passed
  Review regressions    8 passed
  Roles & throttle     26 passed
-------------------------------------------------------------------------------
  260 passed in 10.75s
```

Hooks in `tests/conftest.py` replace pytest's default report order. Pytest prints
failures first and the counts last, so after a long run the thing you actually
want has scrolled off; here a per-layer summary comes last, with the failures —
full traceback and assertion diff — printed underneath it. A skip prints its
reason, which is almost always "Postgres is unreachable".

Eleven layers, in one run.

**`tests/test_domain.py` — 42 unit tests, no database.** The maths and parsing the
money and Smart Input features depend on: discount-before-tax totals for sales and
purchases, `round2` half-up rounding, line-item validation, the full date-phrase
parser, discount extraction, the heuristic classifier, party/product fuzzy
matching, report period resolution, and password hashing.

**`tests/test_multilingual.py` — 46 tests over Hindi and Kannada.** The same
note written five ways must produce the same event; native digits become
numbers; postpositions are moved; names keep their script; and the awkward cases
are pinned — ಬಾಡಿಗೆ is not split into "to ಬಾಡಿ", a product is not swallowed by
the party beside it, and a shop called "ABC Suppliers" is not read as "rs 10".

**`tests/test_ai_mocked.py` — 26 tests over the AI path, model faked.** Provider
selection and precedence, what the prompt asks for, and above all what happens
when the model answers badly: markdown fences, prose around the JSON, truncated
objects, wrong field types, a provider that raises. Every one must degrade to
the built-in parser rather than reaching the shopkeeper. No network, no key, no
cost.

**`tests/test_alerts.py` — 9 tests over the alert log.** That an alert names its
rule, event and author, that an employee's alert is attributed to the employee,
the severity and unread filters, mark-unread, dismissal, bulk clear, and that a
sourceless alert still renders.

**`tests/test_inbound.py` - 28 tests over orders arriving from outside.** A raw
RFC-822 message and a real Telegram `getUpdates` payload go in; a draft, a queue
entry and eventually a recorded sale with moved stock come out. Covers routing by
token, HTML-only mail, Kannada surviving the mail encoding, deduplication (the
key is the message, not the chat), unroutable mail being dropped rather than
guessed at, and that an employee can work the queue but not erase it.

**`tests/test_dispatch.py` - 8 tests over both dispatch modes.** That inline
applies effects before a write returns, that celery mode enqueues instead, that
the task applies an event and passes its chain on, that a duplicate delivery is
skipped rather than applied twice, that the sweep rescues stranded events and
leaves fresh ones alone, and that a broker which is down does not fail the write.
The broker is faked, so these run offline; one extra test talks to a real Redis
and skips without one.

**`tests/test_event_actor.py` — 6 tests over event authorship.** That a sale
names the person who made it, that a chained stock event inherits the same
author, that an employee's work is attributed to them and not to the owner, and
that authorless system events still serialize.

**`tests/test_pagination.py` — 25 tests over paging.** That every list endpoint
returns an envelope, that pages do not overlap, that a page past the end is
empty rather than an error, and above all that the statistics beside the rows
still describe the whole set when the page is shrunk to one row.

**`tests/test_rbac.py` — 26 tests over roles, invites and throttling.** Every
role against the endpoints that matter for it, from both sides — what it may do
*and* what it must be refused, which is the half that actually proves anything.
Covers the permission table itself, cross-tenant access, the invite round trip
(including revoked and reused tokens), the last-owner guard, and the lockout:
that an owner locks after five failures, that an employee never does, that a
successful sign-in clears the streak, and that the lock doubles.

**`tests/test_api_smoke.py` — 36 tests over every endpoint.** One pass across the
whole HTTP surface: all 54 routes are called the way the SPA calls them and the
response is checked for the shape the client relies on — routing, auth,
serialization, the domain call behind each route, and the event effects that
follow a write (a sale moves stock before the request returns; cancelling it puts
the stock back; a workflow rule raises a notification). Error paths are part of
the sweep too: 401 without a session, 404 for a missing document, 400 for an empty
sale, an unknown event type, an out-of-range tax rate and an empty report period.

The smoke tests need Postgres, so start it first with `docker compose up -d`. They
never touch your development data:

- `tests/conftest.py` drops and recreates a scratch **`smartsme_test`** database
  beside the configured one, and runs `alembic upgrade head` into it — so the
  migrations are smoke-tested as well.
- The demo seed is off and each run signs up its own business, so counts are
  deterministic.
- The background worker is off; the write endpoints drain the event queue inline,
  which is what makes the effects assertable.
- Every AI key is cleared, so Smart Input falls back to its built-in parser and
  OCR reports itself unavailable. **The suite makes no network calls** and costs
  nothing to run.

If Postgres is unreachable the smoke tests skip with a note and the unit tests
still run.

Frontend: `npm run typecheck` and `npm run build` in `frontend/`.

### Lint & format

```bash
cd backend
.venv/Scripts/python -m ruff check .            # lint
.venv/Scripts/python -m ruff format .           # format
```

```bash
cd frontend
npm run format                                  # prettier --write
npm run format:check                            # verify only
```

Ruff is configured in `backend/pyproject.toml` (100 columns, import sorting,
pyupgrade, bugbear) and Prettier in `frontend/.prettierrc.json`. The LLM prompt
files (`app/ai/nlp.py`, `app/ai/ocr.py`) are exempt from the line-length rule so
the prompts stay verbatim.

---

## Deployment

The two halves deploy independently to different kinds of host, because they are
different kinds of program: the SPA is static files, the API is a long-lived
Python process.

```
Browser ──► Vercel (frontend/dist, static)
               │  /api/* rewritten (vercel.json) — same origin, cookie stays first-party
               ▼
            Render / Railway / Fly  (uvicorn app.main:app)
               ▼
            Neon PostgreSQL
```

### 1. Database — Neon

This repo is linked to a Neon project via the Neon CLI. [`neon.ts`](neon.ts)
declares the policy; `.neon` (git-ignored) records the link.

```bash
npm i -g neon@latest && neon login
neon link --project-id <your-project-id> --branch production -y
neon deploy          # applies neon.ts to the branch
```

`neon link` and `neon deploy` write the live credentials into `.env.local`
(git-ignored): `DATABASE_URL` (pooled), `DATABASE_URL_UNPOOLED` (direct),
`NEON_BRANCH`, and the Neon Auth URLs.

> **Convert the scheme before handing the URL to this backend.** Neon emits
> `postgresql://…`; SQLAlchemy here uses psycopg 3, so it needs
> `postgresql+psycopg://…`. Passing Neon's string unchanged fails with
> `ModuleNotFoundError: No module named 'psycopg2'`.
>
> ```
> postgresql://…        →  postgresql+psycopg://…
> ```

Use the **pooled** URL for the running API and the **unpooled** one for
migrations. Apply the schema once:

```bash
cd backend
DATABASE_URL="postgresql+psycopg://…<unpooled host>…/neondb?sslmode=require" alembic upgrade head
```

Verify: `SELECT version_num FROM alembic_version;` returns `0001_initial_schema`,
and `information_schema.tables` lists the 14 business tables.

### 2. Backend — Render, Railway or Fly

Not Vercel: this app runs a background worker thread and holds a database
connection pool across requests, neither of which survives in a serverless
function.

- **Root directory** `backend`
- **Build** `pip install -r requirements.txt`
- **Start** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Environment:

```bash
DATABASE_URL="…-pooler…?sslmode=require"   # the pooled string
AUTH_SECRET="<32+ random chars>"           # python -c "import secrets; print(secrets.token_hex(32))"
CORS_ORIGINS="https://your-app.vercel.app"
SEED_DEMO_DATA=false                       # true only if you want the demo tenant in production
COOKIE_SECURE=true                         # HTTPS
COOKIE_SAMESITE=lax                        # lax works because of the rewrite in step 3
ANTHROPIC_API_KEY="…"                      # optional; enables OCR + smarter NLP
```

Health check: `GET /api/health`.

### 3. Frontend — Vercel

The API client calls **relative** `/api/...` paths, so production needs those
paths to resolve on the same origin. [`frontend/vercel.json`](frontend/vercel.json)
does that with a rewrite — edit `REPLACE-WITH-YOUR-BACKEND-HOST` to your step-2
host before the first deploy.

- **Root Directory** `frontend`  ← set this in Project Settings, or the build fails
- Framework preset, build command and output directory come from `vercel.json`

Because the browser only ever talks to the Vercel origin, the session cookie
stays first-party: no CORS preflight, and `SameSite=lax` is enough. If you
instead point the SPA straight at the API's own domain, you must switch to
`COOKIE_SAMESITE=none` with `COOKIE_SECURE=true`, and some browsers will still
drop the cookie.

### Serverless note

If you do put the API somewhere without a persistent process, set
`DISABLE_WORKER=true` and rely on the synchronous `drain_queue()` that already
runs after every business write. `POST /api/events/drain` is available as a cron
target for retrying dead-lettered events.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused` on startup | Postgres is not running: `docker compose up -d` |
| `relation "businesses" does not exist` | Run `alembic upgrade head` |
| OCR says it needs a vision provider | No API key, or `GROQ_MODEL` is text-only. Use `ANTHROPIC_API_KEY`, or a Groq vision model |
| Parsing feels "dumb" (no dates/discounts) | No API key set, so the regex fallback is running. Settings shows the active engine |
| 401 on every request from the SPA | Cookie blocked: use the Vite proxy in dev, or set `CORS_ORIGINS` + `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` in prod |
| Demo data looks wrong | `docker compose down -v && docker compose up -d && alembic upgrade head` |
| Invoice prints with the dark theme | Print from the invoice page; the handler swaps to light automatically |

---

## Getting an Anthropic API key

1. **console.anthropic.com** → Settings → **API Keys** → Create Key (shown once).
2. Add credit under **Plans & Billing** — API usage is prepaid and billed
   separately from a Claude Pro/Max subscription.
3. Put `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` in `backend/.env`, then restart
   the API.

One key covers both NLP and OCR, since Claude reads images.
