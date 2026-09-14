<#
.SYNOPSIS
    Starts everything SmartSME needs, locally.

.DESCRIPTION
    Brings up the containers (PostgreSQL, Redis, Mailpit), applies any pending
    database migrations, then opens the API and the web app in their own
    PowerShell windows. Safe to run repeatedly.

    On a machine that has never run SmartSME, add -Setup once: it creates the
    Python virtualenv, installs both dependency sets, and writes backend/.env
    from the template. After that, plain .\run-dev.ps1 is all you need.

    Each window stays open when its process stops, so a crash on startup is
    still readable. Close a window, or Ctrl+C in it, to stop that piece.

.PARAMETER Setup
    First-run install: create backend/.venv, pip install, npm install, and copy
    backend/.env.example to backend/.env with a freshly generated AUTH_SECRET.
    Slow (a few minutes) and only needed once.

.PARAMETER Celery
    Run events through Redis and Celery instead of applying them inside the
    request. Opens two extra windows (a worker and the beat scheduler). Use it
    for load testing; leave it off for normal work, where inline dispatch keeps
    the UI immediately consistent.

.PARAMETER WithEmail
    Turn on inbound email collection for this run, pointed at Mailpit. Orders
    mailed to the address on the Inbox page are picked up automatically.

.PARAMETER SkipDocker
    Do not touch the containers. For when Postgres and Redis are already
    running somewhere else.

.EXAMPLE
    .\run-dev.ps1 -Setup
    # first time on a new machine

.EXAMPLE
    .\run-dev.ps1
    # every other time

.EXAMPLE
    .\run-dev.ps1 -WithEmail -Celery
    # the full stack, including inbound mail and background workers

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run-dev.ps1
    # if script execution is blocked on this machine
#>

param(
    [switch]$Setup,
    [switch]$Celery,
    [switch]$WithEmail,
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Warn($message) { Write-Host "    $message" -ForegroundColor Yellow }
function Die($message) {
    Write-Host "    $message" -ForegroundColor Red
    exit 1
}

# --- First-run install -------------------------------------------------------
if ($Setup) {
    Step "Creating the Python virtualenv"
    if (-not (Test-Path $venvPython)) {
        $python = (Get-Command python -ErrorAction SilentlyContinue).Source
        if (-not $python) { Die "Python is not on PATH. Install Python 3.10+ and reopen this terminal." }
        & $python -m venv (Join-Path $backend ".venv")
    }

    Step "Installing backend dependencies (a few minutes)"
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r (Join-Path $backend "requirements.txt")

    Step "Installing frontend dependencies"
    Push-Location $frontend
    try { npm install --silent } finally { Pop-Location }

    $envFile = Join-Path $backend ".env"
    if (-not (Test-Path $envFile)) {
        Step "Writing backend\.env with a generated AUTH_SECRET"
        $secret = & $venvPython -c "import secrets; print(secrets.token_hex(32))"
        (Get-Content (Join-Path $backend ".env.example")) `
            -replace '^AUTH_SECRET=.*$', "AUTH_SECRET=`"$secret`"" |
            Set-Content -Path $envFile -Encoding utf8
    }
    Write-Host ""
}

# --- Pre-flight --------------------------------------------------------------
# Fail here with something readable rather than in a window that flashes shut.
if (-not (Test-Path $venvPython)) {
    Die "No virtualenv at $venvPython. Run: .\run-dev.ps1 -Setup"
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Die "Frontend dependencies are missing. Run: .\run-dev.ps1 -Setup"
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Warn "No backend\.env; the built-in defaults will be used (fine for local work)."
}

function Test-PortBusy([int]$Port) {
    try {
        $null = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

foreach ($p in 8000, 5173) {
    if (Test-PortBusy $p) {
        Warn "Port $p is already in use - that server is probably already running."
        Write-Host "      Find it with:  netstat -ano | findstr :$p" -ForegroundColor DarkGray
    }
}

# --- Containers --------------------------------------------------------------
if (-not $SkipDocker) {
    Step "Starting PostgreSQL, Redis and Mailpit"
    try {
        docker compose up -d | Out-Null
    } catch {
        Die "Docker is not installed, or not on PATH. Install Docker Desktop."
    }
    # PowerShell does not throw when a native command fails, so the exit code has
    # to be read: without this, Docker Desktop being closed showed up thirty
    # seconds later as "PostgreSQL did not become ready", which sends you to the
    # wrong place entirely.
    if ($LASTEXITCODE -ne 0) {
        Die "Could not start the containers. Is Docker Desktop running?"
    }

    # Postgres accepts TCP before it is ready to answer queries, so wait for the
    # database itself rather than the port, or the migration below races it.
    Step "Waiting for PostgreSQL"
    $ready = $false
    foreach ($attempt in 1..30) {
        docker compose exec -T db pg_isready -U smartsme -d smartsme 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { Die "PostgreSQL did not become ready. Check: docker compose logs db" }
}

# --- Schema ------------------------------------------------------------------
# Running this every time is what stops "it works on my machine" after a pull
# that brought a new migration.
Step "Applying database migrations"
Push-Location $backend
try {
    & $venvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Die "Migrations failed. The API would not start cleanly." }
} finally {
    Pop-Location
}

# --- Launch ------------------------------------------------------------------
function Start-DevWindow([string]$Title, [string]$WorkDir, [string]$Command) {
    # -NoExit keeps the window open after the process stops, so the traceback of
    # a crash on startup is still readable.
    $mode = "inline"
    if ($Celery) { $mode = "celery" }
    $prelude = "`$Host.UI.RawUI.WindowTitle = '$Title'; `$env:EVENT_DISPATCH = '$mode';"
    if ($WithEmail) { $prelude += " `$env:EMAIL_INGEST_ENABLED = 'true';" }
    Start-Process -FilePath "powershell" `
        -WorkingDirectory $WorkDir `
        -ArgumentList @("-NoExit", "-Command", "$prelude $Command")
}

Step "Opening the app"
Start-DevWindow -Title "SmartSME API" -WorkDir $backend `
    -Command "& '$venvPython' -m uvicorn app.main:app --reload"

Start-DevWindow -Title "SmartSME web" -WorkDir $frontend `
    -Command "npm run dev"

if ($Celery) {
    # --pool=solo: the default prefork pool does not work on Windows.
    Start-DevWindow -Title "SmartSME worker" -WorkDir $backend `
        -Command "& '$venvPython' -m celery -A app.celery_app worker --loglevel=info --pool=solo -Q smartsme"

    # Beat runs the outbox sweep and the inbound mail poll.
    Start-DevWindow -Title "SmartSME beat" -WorkDir $backend `
        -Command "& '$venvPython' -m celery -A app.celery_app beat --loglevel=info"
}

Write-Host ""
Write-Host "SmartSME is running:" -ForegroundColor Green
Write-Host "  App        http://localhost:5173"
Write-Host "  API docs   http://localhost:8000/docs"
Write-Host "  Mail UI    http://localhost:8025      (Mailpit, for inbound orders)"
if ($Celery) {
    Write-Host "  Events     celery mode - writes return before effects are applied" -ForegroundColor Yellow
} else {
    Write-Host "  Events     inline mode - effects apply before a write returns"
}
if ($WithEmail) {
    Write-Host "  Inbound    email collection ON (POP3 from Mailpit)" -ForegroundColor Yellow
} else {
    Write-Host "  Inbound    email collection off; add -WithEmail to turn it on"
}
Write-Host ""
Write-Host "Demo login: demo@smartsme.app / demo1234" -ForegroundColor DarkGray
