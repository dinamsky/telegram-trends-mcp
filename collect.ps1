param(
    [int]$Hours = 48,
    [int]$Limit = 30
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    throw "Run .\install.ps1 first."
}

& $PythonPath (Join-Path $ProjectRoot "collector.py") `
    --watchlist (Join-Path $ProjectRoot "watchlist.json") `
    --output (Join-Path $ProjectRoot "output") `
    --hours $Hours `
    --limit $Limit
