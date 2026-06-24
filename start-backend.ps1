param(
    [int]$Port = 8000,
    [switch]$Lan,
    [string]$HostAddress = ""
)

$ErrorActionPreference = "Stop"

$backendDir = Join-Path $PSScriptRoot "backend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Backend virtual environment not found: $pythonExe"
}

$selectedPort = $Port
while (Get-NetTCPConnection -LocalPort $selectedPort -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Port $selectedPort is already in use, trying $($selectedPort + 1)..."
    $selectedPort += 1
    if ($selectedPort -gt ($Port + 20)) {
        throw "No free port found between $Port and $selectedPort"
    }
}

Set-Location $backendDir
$bindHost = if ($HostAddress) {
    $HostAddress
} elseif ($Lan) {
    "0.0.0.0"
} else {
    "127.0.0.1"
}

$localIp = (
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.InterfaceAlias -notlike "vEthernet*" -and
        $_.InterfaceAlias -notlike "Loopback*"
    } |
    Select-Object -First 1 -ExpandProperty IPAddress
)

Write-Host "Starting backend on http://127.0.0.1:$selectedPort"
Write-Host "Docs: http://127.0.0.1:$selectedPort/docs"
if ($Lan -or $bindHost -eq "0.0.0.0") {
    if ($localIp) {
        Write-Host "Network URL: http://$localIp`:$selectedPort"
        Write-Host "Network Docs: http://$localIp`:$selectedPort/docs"
    } else {
        Write-Host "Network URL: use this PC's IPv4 address with port $selectedPort"
    }
}
& $pythonExe -m uvicorn app.main:app --reload --host $bindHost --port $selectedPort
