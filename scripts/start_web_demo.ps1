param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 4096
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RepoRoot "backend"
$MobileDir = Join-Path $RepoRoot "mobile"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Wait-HttpOk($Uri, $TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Uri"
}

Require-Command flutter
Require-Command $PythonExe

$dbPassword = if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { "emsalist_dev_pwd" }
$env:EMSALIST_ENVIRONMENT = "development"
$env:EMSALIST_LOG_LEVEL = "INFO"
$env:EMSALIST_LOG_FORMAT = "text"
$env:AUTH_MODE = "local"
$env:JWT_SECRET_KEY = "emsalist-local-dev-key-change-in-production"
$env:DATABASE_URL = "postgresql+asyncpg://emsalist:$dbPassword@127.0.0.1:5432/emsalist"
$env:CORS_ALLOW_ORIGINS = "http://localhost:$WebPort,http://127.0.0.1:$WebPort"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:AI_DRAFT_GENERATION_PROVIDER = "deterministic"
$env:DRAFT_GENERATION_JOB_WORKER_ENABLED = "true"
$env:DRAFT_GENERATION_JOB_POLL_SECONDS = "1"
$env:DOCUMENT_INTELLIGENCE_PROVIDER = "deterministic"
$env:EMSALIST_DEMO_SEED_ENABLED = "1"

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    Push-Location $RepoRoot
    try {
        docker compose up -d postgres
    } finally {
        Pop-Location
    }

    $deadline = (Get-Date).AddSeconds(60)
    do {
        $health = docker inspect -f "{{.State.Health.Status}}" emsalist-db 2>$null
        if ($health -eq "healthy") {
            break
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if ($health -ne "healthy") {
        throw "PostgreSQL container did not become healthy"
    }
} else {
    $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432
    if (-not $tcp.TcpTestSucceeded) {
        throw "Docker is not available and PostgreSQL is not reachable at 127.0.0.1:5432"
    }
}

Push-Location $BackendDir
try {
    & $PythonExe -m alembic upgrade head
    & $PythonExe -m alembic current
    & $PythonExe -m alembic heads
    & $PythonExe -m app.scripts.seed_web_demo

    $healthUrl = "http://127.0.0.1:$ApiPort/health"
    try {
        Wait-HttpOk -Uri $healthUrl -TimeoutSeconds 5
    } catch {
        $stdout = Join-Path $env:TEMP "emsalist-web-demo-backend.out.log"
        $stderr = Join-Path $env:TEMP "emsalist-web-demo-backend.err.log"
        $backend = Start-Process `
            -FilePath $PythonExe `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
            -WorkingDirectory $BackendDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -PassThru
        Wait-HttpOk -Uri $healthUrl -TimeoutSeconds 45
        if ($backend.HasExited) {
            throw "Backend exited during startup; see $stderr"
        }
    }
} finally {
    Pop-Location
}

Push-Location $MobileDir
try {
    flutter pub get
    flutter run -d chrome --web-port=$WebPort `
        --dart-define=APP_ENVIRONMENT=development `
        --dart-define=API_BASE_URL=http://127.0.0.1:$ApiPort
} finally {
    Pop-Location
}
