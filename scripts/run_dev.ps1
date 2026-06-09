# Launch backend + frontend in two new PowerShell windows.
# Usage:
#   .\scripts\run_dev.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Backend  -> http://127.0.0.1:8000"
Write-Host "Frontend -> http://127.0.0.1:5680"

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\backend'; if (Test-Path .venv\Scripts\Activate.ps1) { . .venv\Scripts\Activate.ps1 }; uvicorn app.main:app --reload"
)

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\frontend'; npm run dev"
)
