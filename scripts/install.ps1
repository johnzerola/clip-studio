param(
    [switch]$InstallPrerequisites,
    [switch]$InstallOllama,
    [switch]$SkipShortcut,
    [switch]$Check
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $project '.venv\Scripts\python.exe'

function Install-WithWinget([string]$id) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw "App Installer/WinGet indisponível. Instale $id manualmente." }
    & $winget.Source install --exact --id $id --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "WinGet falhou ao instalar $id." }
    Add-InstalledToolPaths
}

Add-InstalledToolPaths
& (Join-Path $project "desktop/prepare.ps1") -Check:$Check
if (-not (Test-Path -LiteralPath $runtime)) {
    if ($Check) { throw 'Ambiente Python ausente. Execute Instalar.cmd.' }
    $python = Find-Python313
    if (-not $python -and $InstallPrerequisites) {
        Install-WithWinget 'Python.Python.3.13'
        $python = Find-Python313
    }
    if (-not $python) { throw 'Python 3.13 x64 ausente. Use o instalador oficial ou Instalar.cmd --automatico.' }
    & $python -X utf8 (Join-Path $PSScriptRoot 'reuse_runtime.py') $project
    if (Test-Path -LiteralPath $runtime) {
        Write-Host 'Dependências idênticas reaproveitadas, com arquivos compartilhados no disco.'
    } else {
        & $python -m venv (Join-Path $project '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente Python.' }
    }
}

if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or
    -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
    if ($Check -or -not $InstallPrerequisites) { throw 'FFmpeg e FFprobe ausentes. Use Instalar.cmd --automatico.' }
    Install-WithWinget 'Gyan.FFmpeg'
}

if (-not $Check) {
    if ($InstallOllama -and -not (Get-Command ollama.exe -ErrorAction SilentlyContinue)) {
        Install-WithWinget 'Ollama.Ollama'
    }
    $reuseMarker = Join-Path $project '.venv/reused-requirements.sha256'
    if (Test-Path -LiteralPath $reuseMarker) {
        $existingHash = (Get-Content -LiteralPath $reuseMarker -Raw).Trim()
        $newHash = & $runtime -c "import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())" (Join-Path $project 'requirements.txt')
        if ($LASTEXITCODE -ne 0 -or $newHash -ne $existingHash) { throw 'Dependências diferentes. Execute o instalador em uma nova pasta.' }
    } else {
        & $runtime -m pip install --disable-pip-version-check -r (Join-Path $project 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências Python.' }
    }
}
& $runtime -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependências inconsistentes.' }
& $runtime -X utf8 (Join-Path $PSScriptRoot 'check.py')
if ($LASTEXITCODE -ne 0) { throw 'Falha na verificação de runtime.' }
if (-not $Check) {
    & $runtime -X utf8 (Join-Path $project 'gta_kit_update.py')
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'O Kit GTA 6 incluído já pode ser usado com gameplay próprio. Para tentar novamente, execute Instalar.cmd.'
        $global:LASTEXITCODE = 0
    }
}
if (-not $Check -and -not $SkipShortcut) {
    & (Join-Path $PSScriptRoot 'shortcut.ps1')
}
Write-Host 'Clip Studio verificado. Para preparar o Ollama opcional, abra Configurar IA no painel.'
