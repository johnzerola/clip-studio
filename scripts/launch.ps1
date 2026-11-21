$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
Add-InstalledToolPaths
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Execute Instalar.cmd primeiro.' }
if (Test-Path -LiteralPath (Join-Path $project 'desktop/runtime.sha256')) {
    & (Join-Path $project 'desktop/prepare.ps1') -Check
    $pythonw = Join-Path $project '.venv/Scripts/pythonw.exe'
    $entry = Join-Path $project 'desktop/launch.pyw'
    Start-Process -FilePath $pythonw -ArgumentList @('-X', 'utf8', ('"' + $entry + '"')) -WorkingDirectory $project -WindowStyle Hidden
    exit 0
}
& $runtime -X utf8 (Join-Path $project 'painel.py')
exit $LASTEXITCODE
