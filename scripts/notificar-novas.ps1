<#
.SYNOPSIS
  Mostra uma notificacao do Windows com as vagas novas da ultima coleta.
.DESCRIPTION
  Le job-radar-pilot\output\vagas.jsonl e conta as vagas marcadas STATUS:NEW.
  Destaca as "Mais compativeis" (FIT:READY). Nao envia nada para a internet.
#>
param(
    [string]$Jsonl = (Join-Path (Split-Path $PSScriptRoot -Parent) "job-radar-pilot\output\vagas.jsonl"),
    [switch]$SoResumo
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Jsonl)) {
    Write-Host "Arquivo nao encontrado: $Jsonl"
    exit 1
}

$vagas = Get-Content $Jsonl -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
$novas = @($vagas | Where-Object { $_.match_labels -contains "STATUS:NEW" -and $_.match_labels -notcontains "RELEVANCE:OFF_TOPIC" })
$prontas = @($novas | Where-Object { $_.match_labels -contains "FIT:READY" })

$titulo = "Radar de Vagas"
if ($novas.Count -eq 0) {
    $texto = "Nenhuma vaga nova na ultima coleta."
} else {
    $texto = "$($novas.Count) vaga(s) nova(s); $($prontas.Count) mais compativel(is)."
    $primeira = $prontas | Select-Object -First 1
    if ($primeira) { $texto += " Ex.: $($primeira.title)" }
}

Write-Host "$titulo - $texto"
if ($SoResumo) { exit 0 }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$icone = New-Object System.Windows.Forms.NotifyIcon
$icone.Icon = [System.Drawing.SystemIcons]::Information
$icone.BalloonTipTitle = $titulo
$icone.BalloonTipText = $texto
$icone.Visible = $true
$icone.ShowBalloonTip(10000)
Start-Sleep -Seconds 11
$icone.Dispose()