# SmartSME — Build Guide & Setup

An AI-powered, event-driven business-management platform for SMEs.
This README is the **implementation guide** — it adapts the vision in
[`SmartSME_Developer_Spec_v2.md`](./SmartSME_Developer_Spec_v2.md) onto a modern
Next.js stack and tells you exactly how to run the project from scratch on any
machine.

> The spec describes *what* SmartSME is. This README describes *how* it's built
> and *how* to run it. When the two disagree, this README wins for stack/infra
> decisions (the spec's RabbitMQ + Express + Python-service design has been
> deliberately replaced — see [Architecture](#architecture)).

---

## Tech stack

| Layer | Choice |
|---|---|
| Framework | **Next.js 16** (App Router) — UI, API route handlers, and server actions in one app |
| Language | **TypeScript** |
| Styling | **Tailwind CSS v4** with a Material-3 token layer (see [Design system](#design-system)) |
| Database | **PostgreSQL 16** (local via Docker) |
| ORM / migrations | **Drizzle ORM** + `drizzle-kit` |
| Auth | **Auth.js (NextAuth v5)** — Google OAuth + optional email/password |
| AI | **Anthropic Claude** (`claude-opus-4-8`) — powers OCR + NLP |
| Event bus | **Postgres `events` table + worker** (replaces RabbitMQ — see below) |
| Background worker | A Node process (`tsx`) that drains the events table |

### Why not RabbitMQ / Express / a Python AI service?

The spec was written for a React SPA + Express + RabbitMQ + a separate Python
OCR/NLP service. On this stack all four collapse:

- **Express BFF → Next.js** route handlers + server actions. No separate server.
- **RabbitMQ → a Postgres `events` table.** For an SME's transaction volume this
  gives you publish/consume, retry, dead-letter, **event replay**, and
  failed-event tracking as plain SQL — and one fewer service to run. See
  [Event bus](#event-bus-postgres-not-rabbitmq).
- **Python AI service → Claude, called from Next.js.** Claude's vision does the
  OCR of invoices/screenshots and structured outputs do the NLP intent+entity
  extraction, in a single request. See [Business Input Engine](#business-input-engine-ai).

---

## Architecture

```text
┌───────────────────────────────────────────────┐
│                Next.js 16 app                  │
│                                                │
│  React Server/Client Components (PWA)          │
│  Forms │ NLP input │ OCR upload │ Dashboard    │
│                                                │
│  Route Handlers (/app/api/*) + Server Actions  │
└───────────────┬───────────────────────────────┘
                │  (same DB transaction)
                ▼
        business write  ──►  INSERT into `events`   ◄─ outbox pattern
                │                     │
                ▼                     ▼
        PostgreSQL (Drizzle)     LISTEN/NOTIFY wakes worker
                                      │
                                      ▼
                            ┌──────────────────┐
                            │  Worker process  │
                            │  claims events   │  SELECT … FOR UPDATE
                            │  runs workflow   │  SKIP LOCKED
                            │  rules, retries  │
                            └──────────────────┘
```

The **event bus is a table**, not a broker. A business action (e.g. creating a
sale) writes the row *and* inserts its event in the **same transaction** (the
outbox pattern) — so an event can never be lost or emitted for a change that
didn't commit. A worker then claims and processes events.

---

## Prerequisites

Install these on the machine before anything else:

| Tool | Version | Check |
|---|---|---|
| **Node.js** | 20 LTS or newer | `node -v` |
| **npm** | comes with Node | `npm -v` |
| **Docker Desktop** | latest | `docker --version` |
| **Git** | latest | `git --version` |

You also need:

- An **Anthropic API key** — from <https://console.anthropic.com>.
- **Google OAuth credentials** (only if you enable Google sign-in) — a Client ID
  + Secret from the Google Cloud Console, with
  `http://localhost:3000/api/auth/callback/google` added as an authorized
  redirect URI.

---

## Setup from scratch on a new computer

There are two paths. **Path A** is for when the repo already exists (you've
pushed it to Git). **Path B** bootstraps the project from absolutely nothing.

### Path A — the repo already exists (clone & run)

```bash
# 1. Get the code
git clone <your-repo-url> smartsme
cd smartsme

# 2. Install dependencies
npm install

# 3. Create your local env file and fill it in (see Environment variables)
cp .env.example .env.local
#   → open .env.local and paste your real values

# 4. Start Postgres (Docker must be running)
docker compose up -d

# 5. Apply the database schema
npm run db:migrate      # or: npm run db:push   (for early dev)

# 6. Run the app + the event worker (two terminals)
npm run dev             # terminal 1 → http://localhost:3000
npm run worker          # terminal 2 → drains the events table
```

Open <http://localhost:3000>. That's it.

> **Windows note:** run these in **PowerShell** or **Git Bash**. `cp` works in
> Git Bash; in PowerShell use `Copy-Item .env.example .env.local`. Docker
> Desktop must be started (the whale icon in the tray) before `docker compose up`.

### Path B — bootstrap the project from zero

If the folder is empty and you're creating SmartSME for the first time:

```bash
# 1. Scaffold a Next.js + TypeScript + Tailwind app
npx create-next-app@latest smartsme \
  --typescript --tailwind --app --src-dir --eslint --import-alias "@/*"
cd smartsme

# 2. Install the rest of the stack
npm install drizzle-orm postgres @anthropic-ai/sdk next-auth@beta zod
npm install -D drizzle-kit tsx @types/node

# 3. Add the config files below (docker-compose.yml, drizzle.config.ts,
#    .env.example) and the package.json scripts, then follow Path A from step 3.
```

---

## Environment variables

Create `.env.local` (never commit it). `.env.example` should be committed as the
template:

```bash
# ---- Database ----
DATABASE_URL="postgresql://smartsme:smartsme@localhost:5432/smartsme"

# ---- Auth.js (NextAuth v5) ----
# Generate a secret with:  npx auth secret
AUTH_SECRET=""
# Optional — only if using Google sign-in
AUTH_GOOGLE_ID=""
AUTH_GOOGLE_SECRET=""

# ---- Anthropic ----
ANTHROPIC_API_KEY=""
# Overridable model id; default is Opus 4.8
ANTHROPIC_MODEL="claude-opus-4-8"
```

> **Never paste real secrets into committed files, chat, or the spec.** Keep them
> in `.env.local` only. If you use a shared secrets store, pull them from there.

---

## Config files

### `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: smartsme
      POSTGRES_PASSWORD: smartsme
      POSTGRES_DB: smartsme
    ports:
      - "5432:5432"
    volumes:
      - smartsme_pgdata:/var/lib/postgresql/data

volumes:
  smartsme_pgdata:
```

### `drizzle.config.ts`

```ts
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./src/db/schema/*",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url: process.env.DATABASE_URL! },
});
```

### `package.json` scripts

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "db:generate": "drizzle-kit generate",
    "db:migrate": "drizzle-kit migrate",
    "db:push": "drizzle-kit push",
    "db:studio": "drizzle-kit studio",
    "worker": "tsx src/worker/index.ts"
  }
}
```

---

## Suggested folder structure

```text
src/
  app/
    (auth)/                 # sign-in pages
    (app)/                  # authenticated app shell (sidebar + topbar)
      dashboard/
      parties/
      products/
      sales/
      purchases/
      expenses/
      input/                # the Smart Business Input Engine UI
      settings/
    api/
      auth/[...nextauth]/   # Auth.js handler
      input/parse/          # NLP + OCR → event endpoint
    globals.css             # Tailwind v4 + M3 design tokens
  db/
    index.ts                # Drizzle client
    schema/                 # one file per domain (parties, products, sales…)
  lib/
    ai/                     # Claude calls (ocr.ts, nlp.ts)
    events/                 # publish() + event types
    workflow/               # rule engine
  worker/
    index.ts                # event-draining loop
```

---

## Database & Drizzle

Drizzle client (`src/db/index.ts`):

```ts
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

const client = postgres(process.env.DATABASE_URL!);
export const db = drizzle(client);
```

Core entities to model as schema files (from the spec §Database Design):
`business`, `user`, `party`, `product`, `inventory`, `sale`, `saleItem`,
`purchase`, `purchaseItem`, `expense`, `invoice`, `workflowRule`,
`workflowExecution`, `eventLog`, `notification`.

Every table carries a `businessId` for multi-tenant isolation.

Workflow after editing a schema file:

```bash
npm run db:generate   # writes a migration to ./drizzle
npm run db:migrate    # applies it
# or npm run db:push for quick, throwaway iteration in early dev
```

---

## Event bus (Postgres, not RabbitMQ)

### The `events` table

```ts
// src/db/schema/events.ts
import { pgTable, uuid, text, jsonb, integer, timestamp } from "drizzle-orm/pg-core";

export const events = pgTable("events", {
  id: uuid("id").primaryKey().defaultRandom(),
  businessId: uuid("business_id").notNull(),
  type: text("type").notNull(),                 // SALE_CREATED, STOCK_UPDATED, …
  payload: jsonb("payload").notNull(),
  status: text("status").notNull().default("pending"), // pending|processing|done|failed|dead
  retryCount: integer("retry_count").notNull().default(0),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  processedAt: timestamp("processed_at"),
  error: text("error"),
});
```

### Publishing (outbox pattern — same transaction as the business change)

```ts
// inside a server action / route handler
await db.transaction(async (tx) => {
  const [sale] = await tx.insert(sales).values(saleData).returning();
  await tx.insert(events).values({
    businessId: sale.businessId,
    type: "SALE_CREATED",
    payload: { saleId: sale.id },
  });
});
// optionally: NOTIFY the worker so it processes instantly
```

### The worker (`src/worker/index.ts`)

Claims events safely with `FOR UPDATE SKIP LOCKED`, runs matching workflow
rules, marks them done or retries with backoff, and dead-letters after N tries.

```ts
import { db } from "@/db";
import { sql } from "drizzle-orm";
import { runWorkflowRules } from "@/lib/workflow";

const MAX_RETRIES = 5;

async function tick() {
  await db.transaction(async (tx) => {
    const rows = await tx.execute(sql`
      SELECT * FROM events
      WHERE status = 'pending'
      ORDER BY created_at
      FOR UPDATE SKIP LOCKED
      LIMIT 10
    `);
    for (const ev of rows) {
      try {
        await runWorkflowRules(ev);              // e.g. SALE_CREATED → update inventory
        await tx.execute(sql`UPDATE events SET status='done', processed_at=now() WHERE id=${ev.id}`);
      } catch (err) {
        const next = ev.retry_count + 1;
        const status = next >= MAX_RETRIES ? "dead" : "pending";
        await tx.execute(sql`
          UPDATE events SET status=${status}, retry_count=${next}, error=${String(err)} WHERE id=${ev.id}
        `);
      }
    }
  });
}

// Poll every second (add LISTEN/NOTIFY later for instant wake-ups)
setInterval(tick, 1000);
console.log("SmartSME event worker running…");
```

This covers the spec's RabbitMQ bullets — publish, consume, retry, dead-letter,
event log, failed-event tracking — plus **event replay** (the rows persist; just
reset `status` to `pending`).

---

## Business Input Engine (AI)

The spec's OCR + NLP + Event Generator, done with Claude. Install: already have
`@anthropic-ai/sdk` and `zod`.

### NLP: plain text → structured event

```ts
// src/lib/ai/nlp.ts
import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY

const BusinessEvent = z.object({
  eventType: z.enum(["SALE_CREATED", "PURCHASE_CREATED", "EXPENSE_ADDED", "ORDER_CREATED"]),
  party: z.string().nullable(),
  product: z.string().nullable(),
  quantity: z.number().nullable(),
  amount: z.number().nullable(),
});

export async function parseCommand(text: string) {
  const res = await client.messages.parse({
    model: process.env.ANTHROPIC_MODEL ?? "claude-opus-4-8",
    max_tokens: 1024,
    messages: [{ role: "user", content:
      `Extract a structured business event from this SME command:\n"${text}"` }],
    output_config: { format: zodOutputFormat(BusinessEvent) },
  });
  return res.parsed_output; // { eventType, party, product, quantity, amount }
}
```

> Example: `"Sold 10 rice bags to Kumar Traders"` →
> `{ eventType: "SALE_CREATED", party: "Kumar Traders", product: "Rice", quantity: 10, amount: null }`

### OCR: invoice / WhatsApp screenshot → structured data

Claude's **vision** reads the image directly — no separate OCR library.

```ts
// src/lib/ai/ocr.ts
import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";

const client = new Anthropic();

const Invoice = z.object({
  party: z.string().nullable(),
  lineItems: z.array(z.object({
    product: z.string(),
    quantity: z.number(),
    unitPrice: z.number().nullable(),
  })),
  total: z.number().nullable(),
});

export async function parseInvoiceImage(base64: string, mediaType: "image/png" | "image/jpeg") {
  const res = await client.messages.parse({
    model: process.env.ANTHROPIC_MODEL ?? "claude-opus-4-8",
    max_tokens: 2048,
    messages: [{
      role: "user",
      content: [
        { type: "image", source: { type: "base64", media_type: mediaType, data: base64 } },
        { type: "text", text: "Extract this invoice/order slip into the schema." },
      ],
    }],
    output_config: { format: zodOutputFormat(Invoice) },
  });
  return res.parsed_output;
}
```

### Confirmation before publishing

The spec's **human-approval step** matters: after `parseCommand` / `parseInvoiceImage`,
show the extracted event to the user for confirmation, and only **then** run the
outbox insert (`SALE_CREATED`, etc.). Never auto-publish an AI-parsed event.

---

## Auth

Auth.js (NextAuth v5) with a Drizzle adapter and database sessions.

```bash
npm install next-auth@beta @auth/drizzle-adapter
npx auth secret   # writes AUTH_SECRET into .env.local
```

Start with **Google** provider (fastest). Add **credentials (email/password)**
if SMEs need non-Google logins — hash passwords with `bcrypt`/`argon2`, store on
the `user` table. Gate every route under `(app)/` behind a session check.

---

## Design system

Reuse the DeepStation Material-3 token approach: define tokens in
`src/app/globals.css` via Tailwind v4's `@theme inline` plus CSS variables, and
flip them under a `.dark {}` block. App shell = sidebar + topbar. Component
patterns: cards, badges, progress, skeletons, empty states. Pick a brand palette
that fits an SME finance tool (clean, trustworthy — avoid the generic
purple-gradient look).

---

## Build order (phased — don't build all 20 modules at once)

1. **Foundation** — Next.js app, Drizzle schema, Docker Postgres, Auth, design tokens, `events` table + worker skeleton.
2. **Business Setup + Party Management** — the tenant + customers/suppliers.
3. **Product & Inventory** — with `STOCK_UPDATED` events + low-stock alerts.
4. **Sales** — create sale → `SALE_CREATED` → worker updates inventory. First full event loop.
5. **Business Input Engine** — NLP + OCR → confirmation → publish. The headline feature.
6. **Dashboard** — KPI cards + charts off the data now flowing.
7. **Purchase, Expense, Accounting, Reporting** — expand outward.
8. **Workflow Engine UI, Notifications, Audit** — the cross-cutting modules.
9. **Stretch:** AI Advisor, Forecasting.

Get **step 4** working end-to-end before widening — one real event loop proves
the whole architecture.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ECONNREFUSED …:5432` | Postgres isn't up. `docker compose up -d`, wait a few seconds, retry. |
| `DATABASE_URL` undefined in `drizzle-kit` | It reads `.env` by default — ensure vars are in `.env.local` **and** loaded (Next loads `.env.local` automatically; for `drizzle-kit` add `import "dotenv/config"` or use `dotenv -e .env.local --`). |
| Auth redirect mismatch | Add `http://localhost:3000/api/auth/callback/google` to the Google OAuth authorized redirect URIs. |
| `ANTHROPIC_API_KEY` errors | Set it in `.env.local`; restart `npm run dev`. |
| Events stuck at `pending` | The worker isn't running — `npm run worker` in a second terminal. |
| Port 3000 in use | `npm run dev -- -p 3001`. |
| Docker volume corrupted / want a clean DB | `docker compose down -v` (⚠️ deletes all local data), then `up -d` + `db:migrate`. |

---

## Daily dev loop

```bash
docker compose up -d     # ensure Postgres is running
npm run dev              # terminal 1
npm run worker           # terminal 2
npm run db:studio        # optional: browse the DB in a GUI
```

Stop Postgres when done: `docker compose down` (keeps data) or
`docker compose down -v` (wipes it).
