param(
    [int]$Hours = 48,
    [int]$Limit = 30
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OutputPath = Join-Path $ProjectRoot "output"
$BaseWatchlistPath = Join-Path $ProjectRoot "watchlist.json"
$PersonalWatchlistPath = Join-Path $ProjectRoot "watchlist.personal.json"

if (-not (Test-Path $PythonPath)) {
    throw "Run .\install.ps1 first."
}

$WatchlistPath = $BaseWatchlistPath
if (Test-Path $PersonalWatchlistPath) {
    $WatchlistPath = $PersonalWatchlistPath
    Write-Host "Using private personalized watchlist: $PersonalWatchlistPath"
} else {
    Write-Host "Using base watchlist: $BaseWatchlistPath"
}

& $PythonPath (Join-Path $ProjectRoot "collector.py") `
    --watchlist $WatchlistPath `
    --output $OutputPath `
    --hours $Hours `
    --limit $Limit

if ($LASTEXITCODE -ne 0) {
    throw "Collector failed with exit code $LASTEXITCODE"
}

& $PythonPath (Join-Path $ProjectRoot "editorial_policy.py") `
    --input (Join-Path $OutputPath "latest.json") `
    --output (Join-Path $OutputPath "latest.md")

if ($LASTEXITCODE -ne 0) {
    throw "Editorial report failed with exit code $LASTEXITCODE"
}

& $PythonPath (Join-Path $ProjectRoot "visual_policy.py") `
    --input (Join-Path $OutputPath "latest.json") `
    --html (Join-Path $OutputPath "latest.html") `
    --svg (Join-Path $OutputPath "latest.svg")

if ($LASTEXITCODE -ne 0) {
    throw "Visual report failed with exit code $LASTEXITCODE"
}

Write-Host "Done. Reports:"
Write-Host "  $OutputPath\latest.md"
Write-Host "  $OutputPath\latest.html"
Write-Host "  $OutputPath\latest.svg"
