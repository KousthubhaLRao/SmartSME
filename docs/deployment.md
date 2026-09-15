# Deployment

Taking it beyond a laptop.

[&larr; Back to the README](../README.md)

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

Any managed PostgreSQL works; Neon is what was used here. The repo no longer
carries a `neon.ts` - it was a leftover from the Next.js version and was removed
along with the other stale Node tooling. Recreate it only if you want Neon's
infrastructure-as-code:

```bash
npm i -g neon@latest && neon login
neon config init     # writes a fresh neon.ts
neon link --project-id <your-project-id> --branch production -y
neon deploy          # applies neon.ts to the branch
```

Or skip all of it and copy the connection string out of the Neon dashboard.

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
GOOGLE_API_KEY="…"                         # optional, free; smarter NLP + OCR
```

Health check: `GET /api/health`.

### 3. Frontend — Vercel

The API client calls **relative** `/api/...` paths, so production needs those
paths to resolve on the same origin. [`frontend/vercel.json`](../frontend/vercel.json)
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

