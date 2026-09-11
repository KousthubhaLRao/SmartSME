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
- [Environment variables](#environment-variables)
- [Repository layout](#repository-layout)
- [Feature tour](#feature-tour)
- [Architecture](#architecture)
- [Database schema](#database-schema)
- [Event bus & workflow engine](#event-bus--workflow-engine)
- [Smart Input Engine (NLP + OCR)](#smart-input-engine-nlp--ocr)
- [Reports](#reports)
- [Auth](#auth)
- [API reference](#api-reference)
- [Design system](#design-system)
- [Tests](#tests)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

---

## Quick start

You need **Python 3.10+**, **Node 18+**, and **Docker** (for PostgreSQL).

```bash
# 1. Start PostgreSQL
docker compose up -d

# 2. Backend  (terminal 1)
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # then fill in AUTH_SECRET and (optionally) an AI key
alembic upgrade head            # create the schema
uvicorn app.main:app --reload   # http://localhost:8000  (docs at /docs)

# 3. Frontend (terminal 2)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Open <http://localhost:5173> and either create an account or use the seeded demo
login:

| | |
|---|---|
| **Email** | `demo@smartsme.app` |
| **Password** | `demo1234` |

On first boot the API seeds a demo business ("Kirana Fresh Traders") with
products, parties, sales, purchases, expenses, workflow rules and notifications,
then starts the background event worker. Set `SEED_DEMO_DATA=false` to skip it.

To reset everything: `docker compose down -v && docker compose up -d && alembic upgrade head`.

The Vite dev server proxies `/api` to `http://localhost:8000`, which keeps the
session cookie first-party in development (no CORS or SameSite juggling).

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
├── docker-compose.yml          PostgreSQL 16
├── backend/
│   ├── alembic/                migrations (versions/0001_initial_schema.py)
│   ├── alembic.ini
│   ├── pyproject.toml          ruff (lint + format) and pytest config
│   ├── requirements.txt
│   ├── tests/                  pytest (pure domain logic, no database)
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
│       ├── ai/                 client.py · nlp.py · ocr.py
│       │
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
        ├── components/         AppShell, RevenueChart, LineItemsEditor, ui/*
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

### Reports (`/reports`)
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

## Event bus & workflow engine

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

## Smart Input Engine (NLP + OCR)

`app/ai/client.py` is a **provider-agnostic** layer over httpx: Anthropic, OpenAI
(or any OpenAI-compatible endpoint), Groq and Google Gemini all implement one
`complete(prompt, system, image)` call. `get_provider()` picks the first
configured key in the order anthropic → openai → groq → google, unless
`AI_PROVIDER` forces one. Vision support is reported per model, so a text-only
Groq model correctly disables OCR instead of failing at the API.

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
- `require_user()` guards every route and returns `{user, business}`, which also
  scopes every query to that tenant. Unknown ids return 404 rather than leaking
  existence, and sign-in gives one message for both bad email and bad password.

`AUTH_SECRET` must be 32+ characters in production.

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
.venv/Scripts/python -m pytest tests -q        # 42 unit tests, no database needed
```

Covers the maths and parsing that the money and Smart Input features depend on:
discount-before-tax totals for sales and purchases, `round2` half-up rounding,
line-item validation, the full date-phrase parser, discount extraction, the
heuristic classifier, party/product fuzzy matching, report period resolution, and
password hashing.

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
