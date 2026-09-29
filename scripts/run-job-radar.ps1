[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArguments
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $workspaceRoot 'job-radar-pilot\.venv\Scripts\python.exe'
$localSource = Join-Path $workspaceRoot 'job-radar-pilot\src'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Ambiente isolado ausente. Execute .\scripts\setup.ps1 primeiro."
}
if (-not (Test-Path -LiteralPath $localSource -PathType Container)) {
    throw "Codigo-fonte local ausente em $localSource"
}

$existingPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
    $localSource
} else {
    "$localSource$([IO.Path]::PathSeparator)$existingPythonPath"
}

$forwarded = @($CliArguments)
if ($forwarded.Count -eq 0 -or $forwarded[0].StartsWith('-')) {
    $forwarded = @('collect') + $forwarded
}

& $venvPython -m job_radar.cli @forwarded
exit $LASTEXITCODE
