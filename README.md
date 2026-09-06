# SmartSME

An AI-assisted, event-driven business-management platform for small and medium
businesses. Shopkeepers record sales, purchases and expenses either through
normal forms or by **typing a plain-language note / snapping a photo of a bill** —
the Smart Input Engine turns that into a structured business event, shows it for
confirmation, and publishes it onto an internal event bus that updates inventory,
party balances and alerts.

Everything runs from one Next.js process. `npm install && npm run dev` is enough:
no database server, no Docker, no API key required to start.

---

## Contents

- [Quick start](#quick-start)
- [Environment variables](#environment-variables)
- [Feature tour](#feature-tour)
- [Architecture](#architecture)
- [Database schema](#database-schema)
- [Event bus & workflow engine](#event-bus--workflow-engine)
- [Smart Input Engine (NLP + OCR)](#smart-input-engine-nlp--ocr)
- [Reports & PDF export](#reports--pdf-export)
- [Auth](#auth)
- [Design system](#design-system)
- [Project layout](#project-layout)
- [Scripts](#scripts)
- [Deploying to Vercel](#deploying-to-vercel)
- [Troubleshooting](#troubleshooting)

---

## Quick start

```bash
npm install
npm run dev
```

Open <http://localhost:3000> and either create an account or use the seeded demo
login:

| | |
|---|---|
| **Email** | `demo@smartsme.app` |
| **Password** | `demo1234` |

On first boot the app automatically:

- starts an **embedded PostgreSQL** (PGlite) in `./.pgdata` — nothing to install,
- applies the Drizzle migrations in `./drizzle`,
- seeds a demo business ("Kirana Fresh Traders") with products, parties, sales,
  purchases, expenses, workflow rules and notifications,
- starts the **event worker in-process**, draining the `events` table every second.

To reset the demo data, delete `./.pgdata` and restart.

### Optional: a real PostgreSQL

```bash
docker compose up -d            # Postgres on :5432
# add to .env:
# DATABASE_URL="postgresql://smartsme:smartsme@localhost:5432/smartsme"
npm run db:migrate              # apply migrations
npm run dev                     # terminal 1
npm run worker                  # terminal 2 (standalone worker)
```

With `DATABASE_URL` set the app uses postgres-js and the worker can run as its
own process. With PGlite (no `DATABASE_URL`) the worker runs inside the Next
server, because a separate process cannot share the embedded database.

---

## Environment variables

Copy `.env.example` to **`.env`** and fill in what you need. Everything is
optional for local development.

```bash
# ---- Database ----
# Unset  -> embedded PGlite in ./.pgdata (zero setup)
# Set    -> a real PostgreSQL server
DATABASE_URL=""

# ---- Auth ----
# Any long random string, 32+ chars. Required in production.
AUTH_SECRET="..."

# ---- AI provider (optional; enables smarter NLP and all OCR) ----
# Set ONE key. If several are set, the first in this order wins,
# or force one with AI_PROVIDER=anthropic|openai|groq|google
ANTHROPIC_API_KEY=""
ANTHROPIC_MODEL="claude-opus-4-8"       # override with a current model, e.g. claude-sonnet-5

OPENAI_API_KEY=""
OPENAI_BASE_URL="https://api.openai.com/v1"   # also OpenRouter, Together, Ollama…
OPENAI_MODEL="gpt-4o-mini"

GROQ_API_KEY=""
# The code default (llama-3.3-70b-versatile) is text-only, so OCR needs a
# vision model like the one .env.example ships:
GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"

GOOGLE_API_KEY=""
GEMINI_MODEL="gemini-2.0-flash"
```

**Without an API key** the app still runs: text input falls back to a built-in
regex parser, and image OCR is disabled with an explanatory message.

`.env` is gitignored, so these values are **not** deployed automatically — see
[Deploying to Vercel](#deploying-to-vercel).

---

## Feature tour

### Dashboard
Six KPI cards (sales, purchases, expenses, inventory value, receivable, payable),
each clicking through to its page. Revenue trend chart, a heuristic
**business-health score** (inventory / revenue / expenses / cash flow), Recent
Sales and Recent Purchases side by side, and a low-stock "Needs attention" panel.

### Smart Input (`/input`)
Two modes:

- **Natural language** — type `Sold 10 rice bags to Kumar Traders` and hit Parse.
- **Image / OCR** — upload an invoice, order slip or WhatsApp screenshot.

Either way you land on a **confirmation screen** with the extracted party, line
items, discount and date, all editable, before anything is written. Typed text
and the parsed draft both survive navigating away and back (sessionStorage),
until the draft is published.

### Sales & Purchases
Full list with source badge (Form / AI·Text / AI·OCR) and payment status. Click
**any row** to open a detail modal with the line items, totals and a
click-to-edit transaction date. Inline "Record payment" and "Cancel" actions;
cancelling reverses inventory and the party balance. Sales additionally have a
printable invoice page at `/sales/[id]`.

Both support **discounts** (flat amount or percentage), applied to the subtotal
before tax, with a live preview while you type and a hard block when the discount
exceeds the sale value.

### Transaction dates
Every sale and purchase carries a business `date` separate from `created_at`. It
defaults to today, can be set when creating the record, and corrected afterwards
from the detail modal — for entries logged late. Lists, charts, analytics and
reports all key off this date.

### Parties (`/parties`)
Customers and suppliers with running balances. Each party row expands to show the
individual unpaid invoices/bills behind its balance, with **"Pay all"** per party
and **"Mark all as paid"** for all receivables or all payables. Phone numbers use
a country-code dropdown (202 countries).

### Products, Expenses, Notifications
Inventory with stock, HSN/SKU, low-stock thresholds and stock-movement history;
categorised expenses with their own dates; an alerts inbox fed by the workflow
engine.

### Reports (`/reports`)
- KPI cards and a **revenue chart** with a Y axis, hover tooltips showing exact
  values, and a range selector (last week / month / 3 / 6 months / year) that
  buckets daily, weekly or monthly as appropriate.
- Top products, top customers, expenses by category, cash-flow summary.
- **Downloadable reports** — see below.

### Workflow (`/workflow`) and Event bus (`/events`)
Toggle built-in rules or add your own `WHEN <event> [condition] THEN <action>`
rule. The event bus page shows events flowing `pending → done`, with retry,
dead-letter and replay, and auto-refreshes.

---

## Architecture

```
Browser (React 19, Server Components + Server Actions)
   │
   ├── Server Action ──► Domain layer (src/lib/domain/*)
   │                        │
   │                        ├── writes business rows          ┐ one
   │                        └── publishes an event row        ┘ transaction
   │                                    │
   │                            events table (outbox)
   │                                    │
   │                        Worker (src/worker/loop.ts)
   │                        claims → runs workflow rules → retries → dead-letters
   │                                    │
   │                        inventory · party balances · notifications
   │
   └── Smart Input ──► src/lib/ai (provider-agnostic NLP + OCR)
                            │
                       human confirmation ──► same domain layer
```

**Why no RabbitMQ / Express / separate Python service?** The event bus is the
`events` table using the **transactional outbox pattern**: the business rows and
the event are committed together, so an event can never be lost or emitted for a
write that rolled back. A worker claims rows in batches, retries with a counter
and dead-letters after 5 attempts — the same guarantees a broker gives, without a
second piece of infrastructure. AI runs in server actions rather than a Python
service. The result is a **modular monolith with an event-driven core**: domains
are cleanly separated and could be extracted into services if scale ever demanded
it.

Key numbers (`src/worker/loop.ts`): `POLL_MS = 1000`, `BATCH = 20`,
`MAX_RETRIES = 5`.

---

## Database schema

Drizzle ORM, one schema file per domain in `src/db/schema/`.

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
| `events` | The outbox: type, JSON payload, status, retry count, error |
| `workflow_rules` / `workflow_executions` | Rule definitions and their audit trail |
| `notifications` | Alerts surfaced in the bell menu |

Positive `parties.balance` means *they owe us* (customer) or *we owe them*
(supplier). Migrations live in `./drizzle` and are applied automatically on boot.

---

## Event bus & workflow engine

Event types (`src/lib/events/types.ts`): `SALE_CREATED`, `PURCHASE_CREATED`,
`STOCK_UPDATED`, `EXPENSE_ADDED`, `PAYMENT_RECEIVED`, `ORDER_CREATED`.

Publishing uses the outbox pattern — `publish(tx, …)` takes the **same
transaction** as the business write:

```ts
await db.transaction(async (tx) => {
  const [row] = await tx.insert(s.sales).values({ … }).returning();
  await tx.insert(s.saleItems).values(…);
  await publish(tx, businessId, "SALE_CREATED", { saleId: row.id });
  return row;
});
await drainQueue();   // process now, so the UI is correct on return
```

Built-in rules seeded per business (`src/lib/workflow/defaults.ts`):

| Rule | When | Then |
|---|---|---|
| Update inventory on sale | `SALE_CREATED` | `update_inventory` |
| Low-stock restock alert | `STOCK_UPDATED` | `restock_alert` |
| Flag high-value expense | `EXPENSE_ADDED` | `flag_expense` |
| Unpaid sale reminder | `SALE_CREATED` | `notify` |

Every rule run is recorded in `workflow_executions`, visible on `/workflow`.

---

## Smart Input Engine (NLP + OCR)

`src/lib/ai/client.ts` is a **provider-agnostic** layer: Anthropic, OpenAI (or
any OpenAI-compatible endpoint), Groq and Google Gemini all implement one
`complete({ system, prompt, image })` interface. `getProvider()` picks the first
configured key in the order anthropic → openai → groq → google, unless
`AI_PROVIDER` forces one.

### Text (`src/lib/ai/nlp.ts`)

1. One prompt asks the model for strict JSON: `eventType`, `party`, `product`,
   `quantity`, `amount`, `category`, `allInventory`, `discountType`,
   `discountValue`, `date`.
2. `extractJson()` pulls the first `{…}` out of the reply and `normalize()`
   validates every field.
3. **If no API key is set, or the call fails**, it falls back to
   `heuristicParse()` — a dependency-free regex parser covering the same fields.

Understood today, among others:

| You type | It extracts |
|---|---|
| `Sold 10 rice bags to Kumar Traders` | sale, qty 10, product Rice, party Kumar Traders |
| `Purchase 50 sugar packets from ABC Suppliers` | purchase (party type corrects direction) |
| `Paid electricity bill 3200` | expense, category Utilities |
| `Sell everything to Anita Stores at 10% discount` | one line per in-stock product, 10% discount |
| `Sold 4 litres cooking oil to Shree on 20th August 2026` | date `2026-08-20` |

Dates accept `20th August 2026`, `20 aug`, `3 sept`, `August 20 2026`,
`20/08/2026`, `2026-08-20`, `today`, `yesterday`, `day before yesterday`. With no
date stated it defaults to today.

### Images (`src/lib/ai/ocr.ts`)

The same provider, with the image attached, returns `party`, `docType`,
`lineItems`, `total`, `date`, `discountType`, `discountValue`. **OCR requires a
vision-capable provider — there is no offline fallback.**

### Grounding (`src/app/(app)/input/actions.ts`)

Both paths then run the same matching step:

- **Party matching** — `bestMatch()` tries exact (normalised), substring, then
  token-subset, so "Anita", "anita stores." and "ANITA STORES" all resolve.
- **Direction correction** — a matched party's own type is authoritative, so a
  named customer forces `sale` even if the model guessed `purchase`.
- **Product matching** to catalogue items, falling back to a custom line.
- **"Entire inventory"** expands to one line per in-stock product.

Nothing is written until you confirm on screen.

---

## Reports & PDF export

`src/lib/reports.ts` builds a report for a **type** (sales, purchases, expenses,
or everything consolidated) over a **period**: today, last 7 days, this month,
last month, last 3 / 6 months, this year, last 12 months, or a custom range.

`src/app/(app)/reports/report-download.tsx` renders it to a real **PDF**
(jsPDF + autoTable, landscape A4) or **CSV**. The PDF has a business header,
period, summary block, one table per section, and page numbers.

Two deliberate details: cancelled documents are **listed but excluded from
totals**, and amounts are printed as plain grouped numbers with the currency
stated once in the header — the PDF core fonts have no `₹` glyph. jsPDF is
dynamically imported, so it only downloads when you actually export.

Invoices print in **light mode regardless of the app theme**: the print handler
temporarily removes the `.dark` class, and the app chrome is hidden with
`print:hidden`, so only the invoice reaches the page.

---

## Auth

Self-contained email + password, no external provider:

- **PBKDF2** hashing via Web Crypto (`src/lib/auth/password.ts`).
- **Signed JWT session cookie** via `jose`, httpOnly, 30 days
  (`src/lib/auth/session.ts`).
- `requireUser()` guards every `(app)` route and returns `{ user, business }`,
  which also scopes every query to that business.

`AUTH_SECRET` must be 32+ characters in production; a dev fallback is used
locally.

---

## Design system

Tailwind v4 with CSS custom properties in `src/app/globals.css`. Light is the
default; a `.dark` class on `<html>` flips the tokens, set before paint by an
inlined script to avoid a flash. No component library — `src/components/ui/*`
holds small primitives (Button, Card, Table, Modal, Input, Badge), and
`src/components/icons.tsx` is a dependency-free stroke icon set.

The sidebar is resizable by dragging the handle on its edge, and collapses to an
icon-only rail when that handle is clicked; both the width and the collapsed
state persist.

---

## Project layout

```
src/
├── app/
│   ├── (app)/                 authenticated area (shared AppShell)
│   │   ├── dashboard/ input/ sales/ purchases/ products/
│   │   ├── parties/ expenses/ reports/ workflow/ events/
│   │   ├── notifications/ settings/
│   │   └── layout.tsx
│   ├── (auth)/                sign-in, sign-up
│   ├── api/worker/            manual queue drain (serverless cron)
│   └── globals.css            design tokens + print rules
├── components/                app shell, dialogs, ui primitives
├── db/
│   ├── schema/                one file per domain
│   ├── index.ts               driver selection (PGlite or postgres-js)
│   └── seed.ts                demo data
├── lib/
│   ├── ai/                    client.ts · nlp.ts · ocr.ts
│   ├── auth/                  password, session, current-user
│   ├── domain/                sales, purchases, payments, products, parties, expenses
│   ├── events/                publish + types
│   ├── workflow/              engine, defaults, labels
│   ├── analytics.ts           dashboard/report aggregates
│   ├── reports.ts             downloadable report builder
│   ├── countries.ts           dial codes for the phone field
│   └── utils.ts               money, dates, rounding
└── worker/                    loop.ts (drain) + index.ts (standalone)
```

Each route folder keeps its own `actions.ts` (server actions) next to its page.

---

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | App + in-process event worker; auto-migrates and seeds |
| `npm run build` / `npm start` | Production build / serve |
| `npm test` | Unit tests (`node:test` via tsx) for totals and analytics |
| `npm run worker` | Standalone worker (real-Postgres setups only) |
| `npm run db:generate` | Generate a migration after editing `src/db/schema/*` |
| `npm run db:migrate` | Apply migrations |
| `npm run db:push` | Push schema directly (throwaway dev iteration) |
| `npm run db:studio` | Browse the database in Drizzle Studio |

---

## Deploying to Vercel

Vercel is serverless, so two things matter.

**1. Set environment variables** (Project → Settings → Environment Variables, for
Production *and* Preview), then **redeploy** — env changes do not apply to
existing deployments:

| Name | Value |
|---|---|
| `DATABASE_URL` | A Neon **pooled** connection string (the `-pooler` host). Required: Vercel's filesystem is read-only, so PGlite cannot run there. |
| `AUTH_SECRET` | A long random string (`openssl rand -hex 32`) |
| `ANTHROPIC_API_KEY` | Optional but recommended — enables LLM parsing **and** OCR |
| `ANTHROPIC_MODEL` | e.g. `claude-sonnet-5` |

Because `.env` is gitignored it is never uploaded. If you skip the AI key,
deployed text input silently drops to the regex fallback and OCR fails with
"Image OCR needs an AI provider that can read images".

**2. Apply migrations once:** `npm run db:migrate` against the deployed database.
The app also attempts migrations on boot, but running it explicitly is cleanest.

**Events on serverless:** a polling worker cannot run in a function, so business
writes **drain the queue synchronously** within the request. The optional
`/api/worker` endpoint drains stragglers — point a Vercel Cron at it and set
`CRON_SECRET` to require `Authorization: Bearer <secret>`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| OCR says it needs a vision provider | No API key is configured, or `GROQ_MODEL` is a text-only model. Set `ANTHROPIC_API_KEY`, or a Groq vision model. |
| Parsing feels "dumb" (no dates/discounts) | No API key set, so the regex fallback is running. The Smart Input footer shows which engine parsed it. |
| 500 on Vercel | Almost always a missing `DATABASE_URL` or `AUTH_SECRET`. |
| Demo data looks wrong | Delete `./.pgdata` and restart to reseed. |
| Schema changed but the DB did not | `npm run db:generate` then `npm run db:migrate`. |
| Invoice prints with the dark theme | Print from the invoice page; the handler swaps to light automatically. |

---

## Getting an Anthropic API key

1. **console.anthropic.com** → Settings → **API Keys** → Create Key (shown once).
2. Add credit under **Plans & Billing** — API usage is prepaid and billed
   separately from a Claude Pro/Max subscription.
3. Put `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` in `.env` locally and in the
   Vercel dashboard for the deployment, then restart / redeploy.

One key covers both NLP and OCR, since Claude reads images.
