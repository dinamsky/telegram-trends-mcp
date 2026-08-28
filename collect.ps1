param(
    [int]$Hours = 48,
    [int]$Limit = 30
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    throw "Сначала выполните .\install.ps1"
}

& $PythonPath (Join-Path $ProjectRoot "collector.py") `
    --watchlist (Join-Path $ProjectRoot "watchlist.json") `
    --output (Join-Path $ProjectRoot "output") `
    --hours $Hours `
    --limit $Limit
