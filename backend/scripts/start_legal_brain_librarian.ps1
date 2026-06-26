param()

$ErrorActionPreference = 'SilentlyContinue'

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

$python = $null
if (Test-Path .\.venv\Scripts\python.exe) {
    $python = .\.venv\Scripts\python.exe
}
if (-not $python) {
    $python = "python"
}

$script = "backend\scripts\legal_brain_librarian_agent.py"
if (-not (Test-Path $script)) {
    Write-Error "Agent script not found: $script"
    exit 1
}

Write-Host "Starting Legal Brain Librarian Agent in watch mode..."
& $python $script --watch --interval 300