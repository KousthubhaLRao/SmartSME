# Performance and load testing

Indexes, pagination, pool sizing, and driving the whole app with Locust.

[&larr; Back to the README](../README.md)

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

