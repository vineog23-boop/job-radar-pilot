$ErrorActionPreference = "Stop"

$raiz = $PSScriptRoot
$python = Join-Path $raiz "job-radar-pilot\.venv\Scripts\python.exe"
$codigoLocal = Join-Path $raiz "job-radar-pilot\src"

if (-not (Test-Path -LiteralPath $python)) {
    # Primeira execucao: prepara o ambiente sozinho, sem exigir comandos.
    Write-Host "Primeira execucao: instalando o ambiente (pode levar alguns minutos)..."
    $setup = Join-Path $raiz "scripts\setup.ps1"
    try {
        & $setup
        $codigoSetup = $LASTEXITCODE
    } catch {
        Write-Host "Falha na instalacao: $($_.Exception.Message)"
        $codigoSetup = 1
    }
    if ($codigoSetup -ne 0 -or -not (Test-Path -LiteralPath $python)) {
        Write-Host "A instalacao nao foi concluida. Confira se o Python 3.13 e o Git estao instalados e tente de novo."
        exit 1
    }
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
