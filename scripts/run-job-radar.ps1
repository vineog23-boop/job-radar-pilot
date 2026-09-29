[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArguments
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $workspaceRoot 'job-radar-pilot\.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Ambiente isolado ausente. Execute .\scripts\setup.ps1 primeiro."
}

$forwarded = @($CliArguments)
if ($forwarded.Count -eq 0 -or $forwarded[0].StartsWith('-')) {
    $forwarded = @('collect') + $forwarded
}

& $venvPython -m job_radar.cli @forwarded
exit $LASTEXITCODE
