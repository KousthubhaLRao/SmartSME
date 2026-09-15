# Setup and configuration

Installing from a clean clone, every environment variable, and where API keys go.

[&larr; Back to the README](../README.md)

---

## Setting up on a new machine

What to do after cloning or pulling on a machine that has never run SmartSME.

**On Windows, `.\run-dev.ps1 -Setup` does all of this for you** - the steps
below are what it runs, and what to do by hand on macOS or Linux. Nothing here
is optional: the repo deliberately carries no secrets, no virtualenv and no
`node_modules`, so they have to be built locally.

### 1. Install the prerequisites

| Tool | Version | Check it with |
|---|---|---|
| Git | any | `git --version` |
| Python | 3.10 or newer | `python --version` |
| Node.js | 18 or newer | `node -v` |
| Docker Desktop | any, and **running** | `docker ps` |

On Windows, install Python from python.org with **"Add python.exe to PATH"**
ticked, and start Docker Desktop before going further — `docker ps` has to answer
with a table, not an error.

### 2. Get the code

```bash
git clone <repo-url> SmartSME
cd SmartSME
```

### 3. Start PostgreSQL

```bash
docker compose up -d       # Postgres 16 (:5432), Redis 7 (:6379), Mailpit (:1025/:8025/:1110)
docker ps                  # expect smartsme-db-1, smartsme-redis-1 and smartsme-mailpit-1
```

There is no embedded-database fallback: the API exits on startup if it cannot
reach Postgres. Nothing needs to be installed on the host — the database lives
inside the container, and `psql` can be reached with
`docker exec -it smartsme-db-1 psql -U smartsme -d smartsme`.

### 4. Set up the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate              # Windows PowerShell
# source .venv/bin/activate         # macOS / Linux
pip install -r requirements.txt
```

Then create the config, **which the pull does not bring** — `backend/.env` is
git-ignored so that nobody's keys travel through the repo. Every machine makes
its own from the template:

```bash
copy .env.example .env              # Windows;  cp .env.example .env elsewhere
```

Open `backend/.env` and set `AUTH_SECRET` to a long random string. Generate one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

The defaults for everything else already match the Docker database and the Vite
dev server, so `AUTH_SECRET` is the only line that must change. An AI key is
optional — see [step 7](#7-optional-turn-on-the-ai-features).

Create the schema:

```bash
alembic upgrade head
```

### 5. Set up the frontend

```bash
cd ../frontend
npm install
```

### 6. Run it

On Windows, from the repo root - this also starts the containers and applies
migrations, so it is the only command you need:

```powershell
.\run-dev.ps1
```

Or start the two servers by hand, in two terminals:

```bash
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload
cd frontend && npm run dev
```

Open <http://localhost:5173> and sign in as `demo@smartsme.app` / `demo1234`. The
first boot seeds that demo business automatically.

To confirm the whole stack is wired up, run the tests — 78 should pass:

```bash
cd backend
.venv\Scripts\python -m pytest -q
```

### 7. Optional: turn on the AI features

Without a key the app still runs: Smart Input falls back to a built-in regex
parser, and photos need `OCR_SPACE_API_KEY` (free) or a vision key.

**`GOOGLE_API_KEY` is the one to get** — [aistudio.google.com](https://aistudio.google.com/apikey)
issues it free with no card, and the same key covers smarter text parsing *and*
reading handwritten slips including their corrections. `ANTHROPIC_API_KEY` and
`OPENAI_API_KEY` work identically if you have them. The Settings page shows
which provider is live and whether it can read images.

### What the pull does not include

| Path | Why | How to get it |
|---|---|---|
| `backend/.env` | holds secrets | copy `backend/.env.example`, set `AUTH_SECRET` |
| `backend/.venv/` | machine-specific | `python -m venv .venv` + `pip install -r requirements.txt` |
| `frontend/node_modules/` | machine-specific | `npm install` |
| the database | lives in a Docker volume | `docker compose up -d` + `alembic upgrade head` |
| `.env.local`, `.neon` | Neon deployment credentials | not needed to run locally |

### If something goes wrong on the first run

| Symptom | Cause | Fix |
|---|---|---|
| `WinError 10013` on uvicorn, or `address already in use` | port 8000 is taken | `netstat -ano \| findstr :8000`, then stop that process |
| `Port 5173 is in use, trying another one` | another Vite is running | harmless — the proxy still targets :8000 — or stop the other one |
| Postgres container will not start, port 5432 in use | a native PostgreSQL is installed on the host | stop that service, or change the published port in `docker-compose.yml` |
| API exits with a connection error on startup | the container is not running | `docker compose up -d` |
| `alembic` / `uvicorn` "not recognised" | the virtualenv is not active | activate it, or call `.venv\Scripts\python -m uvicorn ...` |
| `.\run-dev.ps1` is blocked | PowerShell execution policy | `powershell -ExecutionPolicy Bypass -File .\run-dev.ps1` |
| `does not provide an export named …` in the browser | Vite cached a module that has since changed | stop the dev server and `npm run dev` again |
| relation "businesses" does not exist | migrations never ran | `alembic upgrade head` |

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

# ---- Reading photographed orders (optional, both free) ----
OCR_SPACE_API_KEY=""          # https://ocr.space/ocrapi - free, printed + handwriting
OCR_SPACE_ENGINE=2

# ---- AI provider (optional; smarter NLP, and OCR that sees corrections) ----
# Set ONE key. If several are set the first below wins, unless AI_PROVIDER
# forces a choice (anthropic | openai | google). An image request picks the
# first configured provider that can actually see.
ANTHROPIC_API_KEY=""
ANTHROPIC_MODEL="claude-sonnet-5"

OPENAI_API_KEY=""
OPENAI_BASE_URL="https://api.openai.com/v1"   # also OpenRouter, Together, Ollama
OPENAI_MODEL="gpt-4o-mini"

GOOGLE_API_KEY=""                             # free, no card - the recommended one
GEMINI_MODEL="gemini-3.5-flash-lite"
```

Model names go stale: both defaults here were 404ing until they were checked
against the live API. If a provider starts refusing every call, list what the
key can actually reach before assuming the code is wrong.

**Without an API key** the app still runs: text input falls back to a built-in
regex parser, and image OCR is disabled with an explanatory message. The Settings
page shows which provider is active and whether it can read images.

---

## Getting an Anthropic API key

1. **console.anthropic.com** → Settings → **API Keys** → Create Key (shown once).
2. Add credit under **Plans & Billing** — API usage is prepaid and billed
   separately from a Claude Pro/Max subscription.
3. Put `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` in `backend/.env`, then restart
   the API.

One key covers both NLP and OCR, since these models read images.
