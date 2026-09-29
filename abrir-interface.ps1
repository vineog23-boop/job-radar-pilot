$ErrorActionPreference = "Stop"

$raiz = $PSScriptRoot
$python = Join-Path $raiz "job-radar-pilot\.venv\Scripts\python.exe"
$codigoLocal = Join-Path $raiz "job-radar-pilot\src"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Ambiente local nao encontrado. Execute .\scripts\setup.ps1 primeiro."
    exit 1
}
if (-not (Test-Path -LiteralPath $codigoLocal -PathType Container)) {
    Write-Error "Codigo-fonte local nao encontrado em $codigoLocal"
    exit 1
}

$pythonPathExistente = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($pythonPathExistente)) {
    $codigoLocal
} else {
    "$codigoLocal$([IO.Path]::PathSeparator)$pythonPathExistente"
}

& $python -m job_radar.webapp
exit $LASTEXITCODE
