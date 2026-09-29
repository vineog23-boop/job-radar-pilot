$ErrorActionPreference = "Stop"

$raiz = $PSScriptRoot
$python = Join-Path $raiz "job-radar-pilot\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Ambiente local nao encontrado. Execute .\scripts\setup.ps1 primeiro."
    exit 1
}

& $python -m job_radar.webapp
exit $LASTEXITCODE
