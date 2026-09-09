# SmartSME — Testing Guide

This project has two kinds of automated tests, both run by Node's built-in test
runner through `tsx`:

- **Unit tests** — pure functions, no database (e.g. `calculateSaleTotals`,
  `round2`, password hashing). Fast, deterministic.
- **Integration tests** (`*.integration.test.ts`) — exercise the real domain
  services (sales, purchases, payments, products, parties, expenses), the
  workflow engine, the event outbox, and analytics against a real database.

## The most important guarantee: tests never touch your real data

Every integration test process runs against a **fresh, in-memory PGlite
database**. Nothing is ever written to your `./.pgdata`, and every row a test
creates disappears when the test process exits. On top of that, each test starts
from an empty database (the harness truncates all tables in `beforeEach`), so
tests can never see or corrupt each other's data.

There is also a hard safety guard: if `DATABASE_URL` is set, the suite **refuses
to run** (it would otherwise be able to truncate a real Postgres database). Unset
`DATABASE_URL` when running tests. See `src/test/env.ts`.

## How to run

From the project root:

```bash
# Run the whole suite (unit + integration)
npm test

# Run one file
npx tsx --test src/lib/domain/sales.integration.test.ts

# Re-run on change while you work
npx tsx --test --watch "src/**/*.test.ts"

# With coverage (Node's built-in coverage)
npx tsx --test --experimental-test-coverage "src/**/*.test.ts"
```

> Windows PowerShell: the quoted glob works as written. If `DATABASE_URL` is set
> in your shell/`.env`, either unset it for the test run, or (not recommended)
> set `TEST_ALLOW_REAL_DB=1` to override the guard.

## What's covered

| Area | File |
|---|---|
| Money/number/date helpers | `src/lib/utils.test.ts` |
| Password hashing | `src/lib/auth/password.test.ts` |
| Sale totals (pure) | `src/lib/domain/sales.test.ts` |
| Purchase totals (pure) | `src/lib/domain/purchases.test.ts` |
| Outstanding math (pure) | `src/lib/analytics.test.ts` |
| Sales lifecycle, overselling, discounts, cancel, replay-safety | `src/lib/domain/sales.integration.test.ts` |
| Purchases lifecycle | `src/lib/domain/purchases.integration.test.ts` |
| Payments, settle-party, settle-all | `src/lib/domain/payments.integration.test.ts` |
| Products, stock adjustments, delete rules | `src/lib/domain/products.integration.test.ts` |
| Parties, phone validation | `src/lib/domain/parties.integration.test.ts` |
| Expenses + high-value flagging | `src/lib/domain/expenses.integration.test.ts` |
| Workflow rules: operators, disabled, restock alerts, dedupe | `src/lib/workflow/engine.integration.test.ts` |
| Event outbox: publish, drain, chaining, dead-letter | `src/lib/events/outbox.integration.test.ts` |
| Analytics totals, health, revenue series | `src/lib/analytics.integration.test.ts` |
| Multi-tenant isolation | `src/lib/domain/tenant-isolation.integration.test.ts` |

## The test harness (`src/test/`)

- **`env.ts`** — forces the in-memory database and the `DATABASE_URL` safety
  guard. Imported first by the other harness files, so it always runs before
  `@/db` loads.
- **`db.ts`** — `setupTestDb()` (call in `beforeEach`) initializes the in-memory
  DB once and wipes it before each test. `truncateAll()` discovers every table at
  runtime, so **new tables are cleaned automatically** — you don't maintain a
  list.
- **`factories.ts`** — small builders (`makeBusiness`, `makeCustomer`,
  `makeSupplier`, `makeProduct`) and read helpers (`getProduct`, `getParty`, …).

## Adding a new test (flexible, by design)

1. Create a file ending in `.test.ts` (use `.integration.test.ts` if it hits the
   database). Put it next to the code it tests.
2. For a DB test, start it like this:

```ts
import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, makeProduct } from "@/test/factories";
import { createSale } from "./sales";

beforeEach(setupTestDb); // fresh, empty in-memory DB for every test

test("does the thing", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const p = await makeProduct(biz.id, { stock: 100 });
  const sale = await createSale(biz.id, {
    items: [{ productId: p.id, description: "Rice", quantity: 1, unitPrice: 10 }],
  });
  assert.equal(sale.invoiceNumber, "INV-0001");
});
```

3. Need a new kind of fixture? Add a builder to `src/test/factories.ts` so other
   tests can reuse it. Keep assertions specific — they double as living
   documentation of how each rule is supposed to behave.

No test data ever needs manual cleanup: the in-memory database is thrown away at
the end of each file, and `beforeEach` clears it between tests.
