# Dev tasks for Windows PowerShell. macOS / Linux / Git Bash: scripts/dev.sh.
#
#   .\scripts\dev.ps1 setup   create backend\.venv, install deps, copy .env examples
#   .\scripts\dev.ps1 seed    load data\catalog into the vector store
#   .\scripts\dev.ps1 api     run the FastAPI app on :8000 (auto-reload)
#   .\scripts\dev.ps1 web     run the Next.js app on :3000
#   .\scripts\dev.ps1 test    backend pytest + frontend lint and build
param(
    [Parameter(Position = 0)][string]$Task,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

function Assert-Venv {
    if (-not (Test-Path $VenvPython)) { throw "backend\.venv not found; run: .\scripts\dev.ps1 setup" }
}

function Copy-IfMissing([string]$From, [string]$To) {
    if (-not (Test-Path $To)) {
        Copy-Item $From $To
        Write-Host "created $($To.Substring($Root.Length + 1)) (fill it in)"
    }
}

switch ($Task) {
    "setup" {
        if (-not (Test-Path (Join-Path $Backend ".venv"))) {
            if (Get-Command py -ErrorAction SilentlyContinue) {
                Invoke-Checked py @("-3.11", "-m", "venv", (Join-Path $Backend ".venv"))
            } else {
                Invoke-Checked python @("-m", "venv", (Join-Path $Backend ".venv"))
            }
        }
        Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
        Invoke-Checked $VenvPython @("-m", "pip", "install", "-r", (Join-Path $Backend "requirements-dev.txt"))
        Push-Location $Frontend; try { Invoke-Checked npm @("ci") } finally { Pop-Location }
        Copy-IfMissing (Join-Path $Backend ".env.example") (Join-Path $Backend ".env")
        Copy-IfMissing (Join-Path $Frontend ".env.example") (Join-Path $Frontend ".env.local")
    }
    "seed" {
        Assert-Venv
        Push-Location $Backend; try { Invoke-Checked $VenvPython (@("scripts\seed_catalog.py") + $Rest) } finally { Pop-Location }
    }
    "api" {
        Assert-Venv
        Push-Location $Backend; try { Invoke-Checked $VenvPython @("-m", "uvicorn", "app.main:app", "--reload", "--port", "8000") } finally { Pop-Location }
    }
    "web" {
        Push-Location $Frontend; try { Invoke-Checked npm @("run", "dev") } finally { Pop-Location }
    }
    "test" {
        Assert-Venv
        Push-Location $Backend; try { Invoke-Checked $VenvPython @("-m", "pytest") } finally { Pop-Location }
        Push-Location $Frontend; try { Invoke-Checked npm @("run", "lint"); Invoke-Checked npm @("run", "build") } finally { Pop-Location }
    }
    default {
        Get-Content $PSCommandPath | Select-Object -Skip 1 -First 7 | ForEach-Object { $_ -replace '^# ?', '' }
        exit 1
    }
}
