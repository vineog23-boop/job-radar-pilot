[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Join-Path $workspaceRoot 'job-radar-pilot'
$upstreamRoot = Join-Path $workspaceRoot 'vendor\Scrapling'
$venvRoot = Join-Path $projectRoot '.venv'
$python313 = 'C:\Users\vine\AppData\Local\Programs\Python\Python313\python.exe'
$expectedRemote = 'https://github.com/D4Vinci/Scrapling.git'
$expectedTag = 'v0.4.15'

if (-not (Test-Path -LiteralPath $python313 -PathType Leaf)) {
    throw "Python 3.13 nao encontrado em $python313"
}

$vendorRoot = Split-Path -Parent $upstreamRoot
New-Item -ItemType Directory -Force -Path $vendorRoot | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $upstreamRoot '.git'))) {
    git clone --branch $expectedTag --depth 1 $expectedRemote $upstreamRoot
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao clonar o Scrapling oficial.' }
}

$origin = (git -C $upstreamRoot remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $origin -ne $expectedRemote) {
    throw "Origem inesperada para Scrapling: $origin"
}

$tag = (git -C $upstreamRoot describe --tags --exact-match).Trim()
if ($LASTEXITCODE -ne 0 -or $tag -ne $expectedTag) {
    throw "O clone deve permanecer fixado em $expectedTag; encontrado: $tag"
}

$commit = (git -C $upstreamRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') {
    throw 'Nao foi possivel validar o commit upstream.'
}

if (-not (Test-Path -LiteralPath (Join-Path $venvRoot 'Scripts\python.exe'))) {
    & $python313 -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente virtual.' }
}

$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$scraplingRequirement = "$upstreamRoot[fetchers]"

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Falha ao atualizar pip na venv.' }

& $venvPython -m pip install --editable $scraplingRequirement
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar Scrapling com fetchers.' }

& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements.in')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias do piloto.' }

& $venvPython -m pip install --editable $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o piloto em modo editavel.' }

$scraplingCli = Join-Path $venvRoot 'Scripts\scrapling.exe'
& $scraplingCli install
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar os navegadores do Scrapling.' }

$lockLines = @(& $venvPython -m pip freeze --all) | Where-Object {
    $_ -notmatch 'job-radar-pilot==0\.1\.0' -and
    $_ -notmatch '^-e .*[\\/]job-radar-pilot$'
}
$lockLines | Set-Content -Encoding utf8 (Join-Path $projectRoot 'requirements.lock.txt')

Write-Output "Scrapling $expectedTag instalado no commit $commit"
Write-Output "Python isolado: $venvPython"
