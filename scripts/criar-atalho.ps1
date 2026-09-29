[CmdletBinding()]
param(
    [string]$Destino = [Environment]::GetFolderPath('Desktop')
)

$ErrorActionPreference = 'Stop'

$raiz = Split-Path -Parent $PSScriptRoot
$alvo = Join-Path $raiz 'Radar de Vagas.cmd'
if (-not (Test-Path -LiteralPath $alvo -PathType Leaf)) {
    throw "Launcher nao encontrado em $alvo"
}
if (-not (Test-Path -LiteralPath $Destino -PathType Container)) {
    throw "Pasta de destino nao encontrada: $Destino"
}

$caminhoAtalho = Join-Path $Destino 'Radar de Vagas.lnk'
$shell = New-Object -ComObject WScript.Shell
$atalho = $shell.CreateShortcut($caminhoAtalho)
$atalho.TargetPath = $alvo
$atalho.WorkingDirectory = $raiz
$atalho.Description = 'Abre o painel do Radar de Vagas'
$atalho.IconLocation = "$env:SystemRoot\System32\shell32.dll,22"
$atalho.Save()

Write-Host "Atalho criado: $caminhoAtalho"
Write-Host 'Agora basta dar dois cliques em "Radar de Vagas" na area de trabalho.'
