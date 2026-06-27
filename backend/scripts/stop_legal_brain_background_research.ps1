# Stop Legal Brain Background Research Agent
$ErrorActionPreference = "SilentlyContinue"

# Project root
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

$LockPath = "backend\app\legal_brain\metadata\background_research.lock"
$StatusPath = "backend\app\legal_brain\metadata\background_research_status.json"

Write-Host "Stopping Legal Brain Background Research Agent..." -ForegroundColor Yellow

# Find processes running the background research agent
$processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'python3.exe'" | Where-Object {
    $_.CommandLine -like "*legal_brain_background_research_agent.py*"
}

if ($processes) {
    foreach ($proc in $processes) {
        Write-Host "Found process with PID: $($proc.ProcessId)" -ForegroundColor Cyan
        Write-Host "  Command: $($proc.CommandLine)" -ForegroundColor Gray
        
        # Try graceful stop first
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "  Process stopped." -ForegroundColor Green
        } catch {
            Write-Host "  Failed to stop process: $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "No running background research agent found." -ForegroundColor Gray
}

# Clean up lock file
if (Test-Path $LockPath) {
    try {
        Remove-Item $LockPath -Force -ErrorAction Stop
        Write-Host "Lock file removed." -ForegroundColor Green
    } catch {
        Write-Host "Failed to remove lock file: $_" -ForegroundColor Red
    }
}

# Update status to not running
if (Test-Path $StatusPath) {
    try {
        $status = Get-Content $StatusPath -Raw | ConvertFrom-Json
        $status.is_running = $false
        $status | ConvertTo-Json -Depth 10 | Set-Content $StatusPath -Encoding UTF8
        Write-Host "Status updated: is_running = false" -ForegroundColor Green
    } catch {
        Write-Host "Failed to update status: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Stop operation completed." -ForegroundColor Green