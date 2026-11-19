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
if (-not (Test-Path -LiteralPath $runtime)) {
    if ($Check) { throw 'Ambiente Python ausente. Execute Instalar.cmd.' }
    $python = Find-Python313
    if (-not $python -and $InstallPrerequisites) {
        Install-WithWinget 'Python.Python.3.13'
        $python = Find-Python313
    }
    if (-not $python) { throw 'Python 3.13 x64 ausente. Use o instalador oficial ou Instalar.cmd --automatico.' }
    & $python -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente Python.' }
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
    & $runtime -m pip install --disable-pip-version-check -r (Join-Path $project 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências Python.' }
}
& $runtime -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependências inconsistentes.' }
& $runtime -X utf8 (Join-Path $PSScriptRoot 'check.py')
if ($LASTEXITCODE -ne 0) { throw 'Falha na verificação de runtime.' }
if (-not $Check -and -not $SkipShortcut) {
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    if ($desktop -and (Test-Path -LiteralPath $desktop)) {
        $destination = Join-Path $desktop 'Clip Studio.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($destination)
        $newTarget = Join-Path $project 'Iniciar.cmd'
        if ($shortcut.TargetPath -and $shortcut.TargetPath -ne $newTarget) {
            $destination = Join-Path $desktop ('Clip Studio (' + (Split-Path $project -Leaf) + ').lnk')
            $shortcut = $shell.CreateShortcut($destination)
        }
        $shortcut.TargetPath = $newTarget
        $shortcut.WorkingDirectory = $project
        $shortcut.Description = 'Capture, edite e revise clipes no Clip Studio'
        $shortcut.Save()
        Write-Host "Atalho: $destination"
    }
}
Write-Host 'Clip Studio verificado. Ollama é opcional. Para o modelo local: ollama pull qwen3:4b.'
