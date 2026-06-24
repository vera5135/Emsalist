$ErrorActionPreference = "Stop"

$backendDir = Join-Path $PSScriptRoot "backend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$script = Join-Path $backendDir "scripts\seed_legal_sources.py"

if (-not (Test-Path $pythonExe)) {
    throw "Backend virtual environment not found: $pythonExe"
}

& $pythonExe $script @args
