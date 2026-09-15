# Architecture and layout

How the pieces fit together, what lives where, and the database schema.

[&larr; Back to the README](../README.md)

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
is the source of truth. See [Event dispatch](events.md#event-dispatch-inline-or-celery).

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

