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

        & $Command @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3, 11), (3, 12)] else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $Candidate
        }
    }

    return $null
}

function Assert-NativeSuccess {
    param([string]$Action)

    if ($LASTEXITCODE -ne 0) {
        throw "$Action завершилось с ошибкой (код $LASTEXITCODE)."
    }
}

$PythonCommand = @(Find-Python)

if (-not $PythonCommand -and -not $SkipPythonInstall) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Python 3.11/3.12 не найден. Устанавливаю Python 3.12 через winget..."
        & winget install --exact --id Python.Python.3.12 --scope user `
            --accept-package-agreements --accept-source-agreements
        Assert-NativeSuccess "Установка Python"
        $PythonCommand = @(Find-Python)
    }
}

if (-not $PythonCommand) {
    throw @"
Python 3.11/3.12 не найден.
Установите Python 3.12 командой:
  winget install --exact --id Python.Python.3.12 --scope user
Затем закройте PowerShell, откройте его снова и повторите запуск install.ps1.
"@
}

$BaseCommand = $PythonCommand[0]
$BaseArgs = @($PythonCommand | Select-Object -Skip 1)

Write-Host "Создаю виртуальное окружение..."
& $BaseCommand @BaseArgs -m venv $VenvPath
Assert-NativeSuccess "Создание виртуального окружения"

if (-not (Test-Path $PythonPath)) {
    throw "Виртуальное окружение не создано: $PythonPath не найден."
}

& $PythonPath -m pip install --upgrade pip
Assert-NativeSuccess "Обновление pip"

& $PythonPath -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
Assert-NativeSuccess "Установка зависимостей"

& $PythonPath -c "import asyncio; from tg_mcp.server import mcp; tools=asyncio.run(mcp.list_tools()); print('MCP OK:', ', '.join(t.name for t in tools))"
Assert-NativeSuccess "Проверка MCP"

Write-Host ""
Write-Host "Установка завершена. Запустите: .\collect.ps1 -Hours 48"
