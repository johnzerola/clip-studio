param([switch]$MigrateOnly)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) { return }
$target = Join-Path $project 'Iniciar.cmd'
$legacy = Join-Path $desktop 'Clip Studio.lnk'
$shell = New-Object -ComObject WScript.Shell
$legacyPointsHere = (Test-Path -LiteralPath $legacy) -and ($shell.CreateShortcut($legacy).TargetPath -eq $target)
if ($MigrateOnly -and -not $legacyPointsHere) { return }

function Is-CodexShortcut([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return $true }
    $existing = $shell.CreateShortcut($path).TargetPath
    if (-not $existing) { return $false }
    if ($existing -eq $target) { return $true }
    $oldUpdater = Join-Path (Split-Path -Parent $existing) 'update_install.py'
    return (Split-Path -Leaf $existing) -eq 'Iniciar.cmd' -and
        (Test-Path -LiteralPath $oldUpdater) -and
        ([IO.File]::ReadAllText($oldUpdater).Contains('johnzerola/clip-studio'))
}

$destination = Join-Path $desktop 'Codex.lnk'
if (-not (Is-CodexShortcut $destination)) { $destination = Join-Path $desktop 'Codex - Edicao de video.lnk' }
if (-not (Is-CodexShortcut $destination)) { throw 'Já existe um atalho Codex de outro aplicativo.' }
if ($legacyPointsHere -and -not (Test-Path -LiteralPath $destination)) {
    [IO.File]::Move($legacy, $destination)
}
$shortcut = $shell.CreateShortcut($destination)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $project
$shortcut.Description = 'Codex de edicao de video, antigo Clip Studio'
$shortcut.Save()
Write-Host "Atalho: $destination"
