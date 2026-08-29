param(
    [Parameter(Mandatory=$true)]
    [string]$AnalysisDir,
    [int]$MaxChannels = 100,
    [int]$ResolveLimit = 140,
    [int]$Concurrency = 3
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    throw "Run .\install.ps1 first."
}

if (-not (Test-Path $AnalysisDir)) {
    throw "Analysis directory not found: $AnalysisDir"
}

$ChannelsPath = Join-Path $AnalysisDir "channels.json"
$ForwardsPath = Join-Path $AnalysisDir "forward_stats.json"

if (-not (Test-Path $ChannelsPath)) {
    throw "channels.json not found in: $AnalysisDir"
}

if (-not (Test-Path $ForwardsPath)) {
    throw "forward_stats.json not found in: $AnalysisDir"
}

Push-Location $ProjectRoot
try {
    & $PythonPath (Join-Path $ProjectRoot "personalize_watchlist.py") `
        --analysis-dir $AnalysisDir `
        --base-watchlist (Join-Path $ProjectRoot "watchlist.json") `
        --output (Join-Path $ProjectRoot "watchlist.personal.json") `
        --report (Join-Path $ProjectRoot "output\personalization_report.md") `
        --max-channels $MaxChannels `
        --resolve-limit $ResolveLimit `
        --concurrency $Concurrency

    if ($LASTEXITCODE -ne 0) {
        throw "Personalization failed with exit code $LASTEXITCODE"
    }

    Write-Host "Done. Private watchlist: $ProjectRoot\watchlist.personal.json"
    Write-Host "Report: $ProjectRoot\output\personalization_report.md"
    Write-Host "collect.ps1 will use the private watchlist automatically."
}
finally {
    Pop-Location
}
