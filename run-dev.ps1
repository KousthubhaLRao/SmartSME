<#
.SYNOPSIS
    Starts the SmartSME development stack.

.DESCRIPTION
    Opens two PowerShell windows: the FastAPI reloader on :8000 and the Vite dev
    server on :5173. Postgres is expected to already be running in Docker
    (`docker compose up -d`); this script checks and tells you if it is not.

    Each window stays open when the server stops, so you can read the error and
    restart with the up arrow. Close a window, or Ctrl+C in it, to stop that
    server.

.EXAMPLE
    .\run-dev.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run-dev.ps1
    # If script execution is blocked on this machine.
#>

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

# --- Pre-flight -------------------------------------------------------------
# Fail here with something readable rather than in a window that flashes shut.
if (-not (Test-Path $venvPython)) {
    Write-Host "No virtualenv at $venvPython" -ForegroundColor Red
    Write-Host "Create it:  cd backend; python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt"
    exit 1
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Frontend dependencies are not installed." -ForegroundColor Red
    Write-Host "Install them:  cd frontend; npm install"
    exit 1
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
        Write-Host "Port $p is already in use - that server is probably already running." -ForegroundColor Yellow
        Write-Host "  Find it with:  netstat -ano | findstr :$p" -ForegroundColor DarkGray
    }
}

# Postgres lives in Docker; without it the API exits on startup.
try {
    $db = docker ps --filter "name=smartsme-db" --format "{{.Names}}" 2>$null
    if (-not $db) {
        Write-Host "The Postgres container is not running. Start it with: docker compose up -d" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Could not reach Docker - is Docker Desktop running?" -ForegroundColor Yellow
}

# --- Launch -----------------------------------------------------------------
function Start-DevWindow([string]$Title, [string]$WorkDir, [string]$Command) {
    # -NoExit keeps the window open after the server stops, so the traceback of
    # a crash on startup is still readable.
    $script = "`$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    Start-Process -FilePath "powershell" `
        -WorkingDirectory $WorkDir `
        -ArgumentList @("-NoExit", "-Command", $script)
}

Start-DevWindow -Title "SmartSME API" -WorkDir $backend `
    -Command "& '$venvPython' -m uvicorn app.main:app --reload"

Start-DevWindow -Title "SmartSME web" -WorkDir $frontend `
    -Command "npm run dev"

Write-Host ""
Write-Host "SmartSME is starting in two windows:" -ForegroundColor Green
Write-Host "  API   http://localhost:8000      (docs at /docs)"
Write-Host "  App   http://localhost:5173"
Write-Host ""
Write-Host "Demo login: demo@smartsme.app / demo1234" -ForegroundColor DarkGray