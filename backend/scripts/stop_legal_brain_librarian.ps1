param()

$ErrorActionPreference = 'SilentlyContinue'

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

$lock = "backend\app\legal_brain\metadata\librarian_agent.lock"
$status = "backend\app\legal_brain\metadata\librarian_status.json"

# Try graceful stop first: remove lock and update status
if (Test-Path $lock) {
    try {
        Remove-Item $lock -Force
        Write-Host "Lock file removed."
    } catch {
        Write-Host "Could not remove lock file: $_"
    }
}

if (Test-Path $status) {
    try {
        $data = Get-Content $status -Raw | ConvertFrom-Json
        $data.is_running = $false
        $data | ConvertTo-Json -Depth 5 | Set-Content $status -Encoding UTF8
        Write-Host "Status updated to not running."
    } catch {
        Write-Host "Could not update status file: $_"
    }
}

# Target only processes running the agent script
$processes = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -like "*legal_brain_librarian_agent.py*"
}

if ($processes) {
    foreach ($proc in $processes) {
        try {
            Stop-Process -Id $proc.ProcessId -Force
            Write-Host "Stopped agent process: $($proc.ProcessId)"
        } catch {
            Write-Host "Could not stop process $($proc.ProcessId): $_"
        }
    }
} else {
    Write-Host "No running agent process found."
}