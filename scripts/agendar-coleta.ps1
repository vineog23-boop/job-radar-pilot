<#
.SYNOPSIS
  Agenda (ou remove) a coleta diaria do Radar de Vagas no Agendador de Tarefas.
.EXAMPLE
  .\agendar-coleta.ps1 -Horario 08:00
  .\agendar-coleta.ps1 -Remover
#>
param(
    [ValidatePattern('^\d{2}:\d{2}$')]
    [string]$Horario = "08:00",
    [switch]$Remover
)

$ErrorActionPreference = "Stop"
$nome = "RadarDeVagas-ColetaDiaria"

if ($Remover) {
    if (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $nome -Confirm:$false
        Write-Host "Agendamento removido."
    } else {
        Write-Host "Nao havia agendamento."
    }
    exit 0
}

$script = Join-Path $PSScriptRoot "coleta-agendada.ps1"
$acao = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$gatilho = New-ScheduledTaskTrigger -Daily -At $Horario
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config `
    -Description "Coleta diaria de vagas (portais de tecnologia) e aviso de vagas novas." -Force | Out-Null
Write-Host "Coleta agendada todos os dias as $Horario (se o PC estiver desligado, roda quando ligar)."
Write-Host "Log: job-radar-pilot\output\coleta-agendada.log"