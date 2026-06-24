$ErrorActionPreference = "Stop"

$rootScript = Join-Path $PSScriptRoot "..\seed-legal-brain.ps1"
& $rootScript @args
