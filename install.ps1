param(
    [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonPath = Join-Path $VenvPath "Scripts\python.exe"

function Find-Python {
    $Candidates = @()

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Candidates += ,@("py", "-3.12")
        $Candidates += ,@("py", "-3.11")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $Candidates += ,@("python")
    }

    $Candidates += ,@(Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
    $Candidates += ,@(Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")

    foreach ($Candidate in $Candidates) {
        $Command = $Candidate[0]
        $PrefixArgs = @($Candidate | Select-Object -Skip 1)

        if (($Command -match "[\\/]") -and -not (Test-Path $Command)) {
            continue
        }

        # Windows may have py.exe installed without any Python runtime behind it.
        # With ErrorActionPreference=Stop its diagnostic on stderr becomes a
        # terminating NativeCommandError, so probe candidates in a protected
        # scope and treat every failure as "candidate unavailable".
        $PreviousErrorActionPreference = $ErrorActionPreference
        $ProbeExitCode = 1
        try {
            $ErrorActionPreference = "SilentlyContinue"
            $null = & $Command @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3, 11), (3, 12)] else 1)" 2>&1
            $ProbeExitCode = $LASTEXITCODE
        }
        catch {
            $ProbeExitCode = 1
        }
        finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }

        if ($ProbeExitCode -eq 0) {
            return $Candidate
        }
    }

    return $null
}

function Assert-NativeSuccess {
    param([string]$Action)

    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE."
    }
}

$PythonCommand = @(Find-Python)

if (-not $PythonCommand -and -not $SkipPythonInstall) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Python 3.11/3.12 was not found. Installing Python 3.12 with winget..."
        & winget install --exact --id Python.Python.3.12 --scope user `
            --accept-package-agreements --accept-source-agreements
        Assert-NativeSuccess "Python installation"
        $PythonCommand = @(Find-Python)
    }
}

if (-not $PythonCommand) {
    throw @"
Python 3.11/3.12 was not found.
Install Python 3.12 with:
  winget install --exact --id Python.Python.3.12 --scope user
Then close PowerShell, open it again, and run install.ps1 once more.
"@
}

$BaseCommand = $PythonCommand[0]
$BaseArgs = @($PythonCommand | Select-Object -Skip 1)

Write-Host "Creating the virtual environment..."
& $BaseCommand @BaseArgs -m venv $VenvPath
Assert-NativeSuccess "Virtual environment creation"

if (-not (Test-Path $PythonPath)) {
    throw "Virtual environment was not created: $PythonPath was not found."
}

& $PythonPath -m pip install --upgrade pip
Assert-NativeSuccess "pip upgrade"

& $PythonPath -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
Assert-NativeSuccess "Dependency installation"

& $PythonPath -c "import asyncio; from tg_mcp.server import mcp; tools=asyncio.run(mcp.list_tools()); print('MCP OK:', ', '.join(t.name for t in tools))"
Assert-NativeSuccess "MCP check"

Write-Host ""
Write-Host "Installation complete. Run: .\collect.ps1 -Hours 48"
