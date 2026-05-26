# Wipe runtime artifacts: SQLite db + snapshots + logs.
# Usage:
#   .\scripts\reset_runtime.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root "runtime"

Write-Host "Wiping runtime artifacts under $runtime ..."

Get-ChildItem -Path $runtime -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne ".gitkeep" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Make sure base subdirs still exist.
foreach ($d in @("snapshots", "logs")) {
    $p = Join-Path $runtime $d
    New-Item -ItemType Directory -Path $p -Force | Out-Null
    if (-not (Test-Path (Join-Path $p ".gitkeep"))) {
        New-Item -ItemType File -Path (Join-Path $p ".gitkeep") -Force | Out-Null
    }
}

Write-Host "Done."
