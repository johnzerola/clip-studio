$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) { return }
$target = Join-Path $project 'Iniciar.cmd'
$legacy = Join-Path $desktop 'Clip Studio.lnk'
$shell = New-Object -ComObject WScript.Shell

function Is-CodexShortcut([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return $true }
    $existing = $shell.CreateShortcut($path).TargetPath
    if (-not $existing) { return $false }
    if ($existing -eq $target) { return $true }
    $parent = Split-Path -Parent $existing
    if (-not $parent) { return $false }
    $oldUpdater = Join-Path $parent 'update_install.py'
    return (Split-Path -Leaf $existing) -in @('Iniciar.cmd', 'Clip Studio.exe', 'Codex.exe') -and
        (Test-Path -LiteralPath $oldUpdater) -and
        ([IO.File]::ReadAllText($oldUpdater).Contains('johnzerola/clip-studio'))
}

function Set-CodexShortcut([string]$destination) {
    $shortcut = $shell.CreateShortcut($destination)
    $shortcut.TargetPath = $target
    $shortcut.Arguments = ''
    $shortcut.WorkingDirectory = $project
    $shortcut.Description = 'Codex de edicao de video, antigo Clip Studio'
    $shortcut.Save()
    Write-Host "Atalho: $destination"
}

$destination = Join-Path $desktop 'Codex.lnk'
if (-not (Is-CodexShortcut $destination)) { $destination = Join-Path $desktop 'Codex - Edicao de video.lnk' }
if (-not (Is-CodexShortcut $destination)) { throw 'Já existe um atalho Codex de outro aplicativo.' }
Set-CodexShortcut $destination
if (Test-Path -LiteralPath (Join-Path $project 'desktop/runtime.sha256')) {
    if (Is-CodexShortcut $legacy) { Set-CodexShortcut $legacy }
    $programs = [Environment]::GetFolderPath('Programs')
    if ($programs -and (Test-Path -LiteralPath $programs)) {
        foreach ($name in @('Codex - Edicao de video.lnk', 'Clip Studio.lnk')) {
            $entry = Join-Path $programs $name
            if (Is-CodexShortcut $entry) { Set-CodexShortcut $entry }
        }
    }
}
