$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
Add-InstalledToolPaths
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Execute Instalar.cmd primeiro.' }
& $runtime -X utf8 (Join-Path $project 'painel.py')
exit $LASTEXITCODE
