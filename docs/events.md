# The event bus and how work gets dispatched

The transactional outbox, the workflow rule engine, and inline vs Celery.

[&larr; Back to the README](../README.md)

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

