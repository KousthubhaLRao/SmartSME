# SmartSME — Architecture & Frontend/Backend Boundary

SmartSME is a **single Next.js application**, not a separate frontend app plus a
separate backend server. Next.js runs the UI (React Server and Client
Components) and the server logic (Server Actions, Route Handlers) in one
codebase and one deployable. A standalone background worker process shares the
same code. This document draws the frontend/backend line clearly *inside* that
one app so everyone knows where each kind of code belongs.

## Why it isn't split into separate `backend/` and `frontend/` folders

A project like a FastAPI backend with a separate React frontend keeps them in
different folders because they are different programs that talk over HTTP.
SmartSME is the opposite on purpose: the UI calls the database through **Server
Actions** (server-side functions invoked directly from components), not through a
REST API. Splitting it into two apps would mean rewriting that data flow as HTTP
endpoints, plus CORS, cross-origin auth, and two build pipelines — a
re-architecture, not a folder move. So the boundary here is by **layer and
folder within one app**, and it is enforced by a simple rule (below) rather than
by a network hop.

## The layers

```
Browser (PWA)
   │  React Server/Client Components  ── UI only
   ▼
Server Actions / Route Handlers      ── thin: auth check, parse input, call a service
   │
   ▼
Domain services (the "backend")      ── all business logic + the only place that
   │                                    reads/writes the database
   ▼
PostgreSQL / embedded PGlite         ── via Drizzle ORM
   ▲
   │  outbox `events` table
Background worker                    ── drains events, runs workflow rules
```

## Folder map

**Frontend (UI) — never touches the database directly**

| Path | Role |
|---|---|
| `src/app/**/page.tsx`, `layout.tsx` | Pages and layouts (routing lives here; must stay under `src/app`) |
| `src/components/**` | Reusable UI components |
| `src/app/globals.css` | Tailwind v4 + design tokens |

**Backend (server-only) — the business logic and data layer**

| Path | Role |
|---|---|
| `src/lib/domain/**` | Business services: sales, purchases, payments, products, parties, expenses, line-items |
| `src/lib/workflow/**` | The rule engine (`engine.ts`), default rules, labels |
| `src/lib/events/**` | The outbox publisher and event types |
| `src/lib/analytics.ts`, `src/lib/reports.ts` | Read-side aggregation |
| `src/lib/auth/**` | Sessions (`jose`) and password hashing |
| `src/lib/ai/**` | The Smart Input engine (NLP + image parsing), provider-agnostic |
| `src/db/**` | Drizzle client, schema, seed |
| `src/worker/**` | The standalone event-draining worker |

**The seam between them**

| Path | Role |
|---|---|
| `src/app/**/actions.ts` | Server Actions — the *only* bridge the UI uses to reach the backend. Keep these thin: check the session, validate input, call a `src/lib/domain` service, return the result. |

## The one rule that keeps the boundary clean

**UI code (`src/app/**/*.tsx`, `src/components/**`) must never import from
`src/db` or call the database directly. It goes through a Server Action, which
calls a domain service in `src/lib`, which is the only layer that touches the
database.**

If you follow that rule, the frontend and backend stay cleanly separated even
though they live in one app: you can reason about, test, and change the backend
(everything in `src/lib`, `src/db`, `src/worker`) without opening a single UI
file — which is exactly why the integration tests in `TESTING.md` can exercise
the whole backend without rendering any React.

## Data & consistency model (backend)

- **Transactional outbox:** a business write and its event are inserted in the
  **same database transaction** (`src/lib/events/publish.ts` called inside a
  `db.transaction`), so an event can never be lost or emitted for an uncommitted
  change.
- **Worker:** `src/worker` (and a synchronous `drainQueue()` after each write)
  claims events with `FOR UPDATE SKIP LOCKED`, runs the matching workflow rules,
  retries with a bounded count, and dead-letters after five failures.
- **Idempotent/replay-safe:** re-processing a SALE/PURCHASE event does not
  double-apply stock or balances (guarded by existing stock movements).
- **Multi-tenant:** every table carries `businessId`; every service scopes its
  queries to it. The isolation tests assert one tenant can never read or mutate
  another's data.

## Database

One database serves as both the system of record and the event queue. It is
**PostgreSQL** when `DATABASE_URL` is set, and an embedded in-process
**PGlite** (zero-setup) when it isn't. Same schema, same Drizzle queries either
way (`src/db/index.ts`).
