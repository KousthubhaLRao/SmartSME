# SmartSME — Getting Started

This is the **built, runnable** SmartSME app (Next.js 15 App Router + TypeScript +
Tailwind v4 + Drizzle + event worker + Claude AI input). It implements the
`SmartSME_Developer_Spec_v2.md` vision on the modern stack described in
[`README.md`](./README.md).

## Run it (zero setup)

```bash
npm install
npm run dev
```

Open <http://localhost:3000> and either **create an account** or use the seeded
demo login:

| | |
|---|---|
| **Email** | `demo@smartsme.app` |
| **Password** | `demo1234` |

That's it. No Docker, no database server, no API key required to start.

On first boot the app automatically:
- spins up an **embedded PostgreSQL** (PGlite) in `./.pgdata` — no install needed,
- applies the Drizzle migrations in `./drizzle`,
- seeds a demo business ("Kirana Fresh Traders") with products, parties, sales,
  purchases, expenses, workflow rules, and notifications,
- starts the **event worker in-process** (drains the `events` table every second).

## What to try

1. **Dashboard** — KPIs, revenue trend, business-health scores, low-stock alerts.
2. **Smart Input** (`/input`) — type `Sold 10 rice bags to Kumar Traders`, hit
   Parse, confirm, and publish. Watch the sale appear and inventory update.
3. **Event bus** (`/events`) — see events flow `pending → done`, with retry &
   replay. This page auto-refreshes.
4. **Sales / Purchases** — create one; the worker updates stock + balances and
   raises low-stock alerts (see the bell / `/notifications`).
5. **Workflow** (`/workflow`) — toggle rules or add your own WHEN → THEN rule.

## Optional upgrades

### Real PostgreSQL (instead of embedded PGlite)

```bash
docker compose up -d          # starts Postgres on :5432
# add to .env.local:
# DATABASE_URL="postgresql://smartsme:smartsme@localhost:5432/smartsme"
npm run db:migrate            # apply migrations to Postgres
npm run dev                   # terminal 1
npm run worker                # terminal 2 (separate worker process)
```

When `DATABASE_URL` is set, the app uses postgres-js and you can run the worker
as its own process (`npm run worker`). With PGlite (no `DATABASE_URL`), the
worker runs inside the Next server automatically — a separate process can't share
the embedded database.

### Claude-powered input (instead of the built-in heuristic parser)

```bash
# add to .env.local:
# ANTHROPIC_API_KEY="sk-ant-..."
# ANTHROPIC_MODEL="claude-opus-4-8"   # optional, this is the default
```

Without a key, the **Smart Input** text parser uses a built-in heuristic engine
(good enough to demo). With a key, it upgrades to Claude for natural-language
parsing **and** unlocks image OCR (invoice / order-slip / WhatsApp screenshots).

### Auth secret

Session cookies are signed with `AUTH_SECRET`. A dev fallback is used if unset;
set a real value for anything beyond local dev:

```bash
# .env.local
AUTH_SECRET="a-long-random-string"
```

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | App + in-process event worker (embedded DB auto-migrates & seeds) |
| `npm run build` / `npm run start` | Production build / serve |
| `npm run worker` | Standalone worker (real-Postgres setups only) |
| `npm run db:generate` | Generate a migration after editing `src/db/schema/*` |
| `npm run db:migrate` | Apply migrations (real Postgres) |
| `npm run db:studio` | Browse the DB in Drizzle Studio |

To reset the demo data, delete `./.pgdata` and restart.

## How it maps to the spec

The spec's RabbitMQ + Express + Python-OCR design is realized on Next.js exactly
as the README describes:

- **Event bus = the `events` table** (outbox pattern). Business writes and their
  events commit in one transaction; a worker claims rows
  (`FOR UPDATE SKIP LOCKED`-style), runs workflow rules, retries with backoff,
  and dead-letters — with **replay** by resetting status. See `/events`.
- **Workflow engine** = configurable WHEN → THEN rules evaluated per event, plus
  always-on core effects (inventory, balances). See `/workflow`.
- **Smart Input Engine** = NLP + OCR via Claude (with a heuristic fallback) →
  validation/matching → **human confirmation** → publish. See `/input`.
- **AI (OCR + NLP)** = Claude called from Next.js server actions
  (`src/lib/ai/`) — no separate Python service.

### Notes on the build (adaptations for zero-setup running)

- **Auth** uses a self-contained email/password + signed-cookie session
  (PBKDF2 via Web Crypto, `jose` JWT) instead of Auth.js/Google OAuth, so it runs
  with no external credentials. Add OAuth later if needed.
- **Database** auto-falls back to **embedded PGlite** when `DATABASE_URL` is
  unset (Docker wasn't required to run this). Set `DATABASE_URL` for Postgres.
- **Worker** runs in-process (Next instrumentation) by default; standalone
  `npm run worker` is for the real-Postgres two-process setup.

## Deploying to Vercel

Vercel is **serverless**, so two things matter:

1. **Set environment variables** in Vercel → Project → Settings → Environment
   Variables (for Production + Preview), then redeploy:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | your Neon **pooled** connection string (the `-pooler` host) — required; without it the app tries embedded PGlite, which can't run on Vercel's read-only filesystem |
   | `AUTH_SECRET` | a long random string (e.g. `openssl rand -hex 32`) |
   | `ANTHROPIC_API_KEY` | optional — enables Claude NLP + OCR |

2. **Apply migrations to your database once** (from your machine, or a build
   step): `npm run db:migrate`. The app also attempts migrations on boot
   (best-effort), but running it explicitly is cleanest.

**How events work on serverless:** the background polling worker can't run in a
serverless function, so business writes **drain the event queue synchronously**
within the request — creating a sale updates inventory/balances and raises alerts
before the response returns. An optional `/api/worker` endpoint drains any
stragglers (e.g. retrying dead-lettered events); point a Vercel Cron at it, and
set `CRON_SECRET` to require `Authorization: Bearer <secret>`.

> If you saw a 500 on Vercel, it was almost always a missing `DATABASE_URL` /
> `AUTH_SECRET`. Set them and redeploy.
