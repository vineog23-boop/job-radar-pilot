<#
.SYNOPSIS
  Coleta agendada: busca so nos portais de tecnologia e avisa das vagas novas.
#>
param([switch]$SemNotificacao)

$raiz = Split-Path $PSScriptRoot -Parent
$saida = Join-Path $raiz "job-radar-pilot\output"
$log = Join-Path $saida "coleta-agendada.log"
New-Item -ItemType Directory -Force -Path $saida | Out-Null

"[$(Get-Date -Format s)] Iniciando coleta agendada" | Add-Content $log -Encoding UTF8
& (Join-Path $PSScriptRoot "run-job-radar.ps1") --output $saida --tech-only *>> $log
$codigo = $LASTEXITCODE
"[$(Get-Date -Format s)] Coleta terminou com codigo $codigo" | Add-Content $log -Encoding UTF8

if (-not $SemNotificacao -and $codigo -in @(0, 3)) {
    & (Join-Path $PSScriptRoot "notificar-novas.ps1")
}
exit $codigo