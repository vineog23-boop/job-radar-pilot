param(
    [string[]]$Fonte,
    [ValidateRange(1, 4)]
    [int]$Workers = 1
)

$ErrorActionPreference = "Stop"

$raiz = $PSScriptRoot
$executarRadar = Join-Path $raiz "scripts\run-job-radar.ps1"
$saida = Join-Path $raiz "job-radar-pilot\output"
$jsonl = Join-Path $saida "vagas.jsonl"

$argumentosRadar = @("--output", $saida, "--workers", $Workers)
foreach ($codigoFonte in $Fonte) {
    $argumentosRadar += @("--source", $codigoFonte)
}

& $executarRadar @argumentosRadar
$codigoColeta = $LASTEXITCODE

if ($codigoColeta -notin @(0, 3)) {
    Write-Error "A busca falhou com o codigo $codigoColeta."
    exit $codigoColeta
}

& $executarRadar validate-output $jsonl
if ($LASTEXITCODE -ne 0) {
    Write-Error "A busca terminou, mas o arquivo JSONL nao passou na validacao."
    exit 1
}

Write-Host ""
Write-Host "Busca concluida e validada."
Write-Host "Vagas para outra IA: $jsonl"
Write-Host "Planilha: $(Join-Path $saida 'vagas.csv')"
Write-Host "Relatorio: $(Join-Path $saida 'relatorio-execucao.json')"

if ($codigoColeta -eq 3) {
    Write-Host "Alguns portais bloquearam a coleta ou mudaram o layout; consulte o relatorio."
}

exit 0
