# Start Legal Brain Background Research Agent in watch mode
param(
    [int]$Interval = 3600,
    [int]$Limit = 5
)

$ErrorActionPreference = "SilentlyContinue"

# Project root
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

# Python interpreter
$PythonExe = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $PythonExe = ".venv\Scripts\python.exe"
} else {
    $PythonExe = "python"
}

$ScriptPath = "backend\scripts\legal_brain_background_research_agent.py"

Write-Host "Starting Legal Brain Background Research Agent..." -ForegroundColor Green
Write-Host "Mode: Watch" -ForegroundColor Cyan
Write-Host "Interval: $Interval seconds" -ForegroundColor Cyan
Write-Host "Limit per topic: $Limit" -ForegroundColor Cyan
Write-Host ""

# Start the process
$process = Start-Process -FilePath $PythonExe -ArgumentList $ScriptPath, "--watch", "--interval", $Interval, "--limit", $Limit -NoNewWindow -PassThru -RedirectStandardOutput "background_research_stdout.log" -RedirectStandardError "background_research_stderr.log"

Write-Host "Agent started with PID: $($process.Id)" -ForegroundColor Green
Write-Host "Logs: background_research_stdout.log, background_research_stderr.log" -ForegroundColor Yellow
Write-Host "Status file: backend\app\legal_brain\metadata\background_research_status.json" -ForegroundColor Yellow