param(
    [int]$Port = 8000,
    [switch]$Lan,
    [string]$HostAddress = ""
)

$ErrorActionPreference = "Stop"

$rootScript = Join-Path $PSScriptRoot "..\start-backend.ps1"
& $rootScript -Port $Port -Lan:$Lan -HostAddress $HostAddress
