Set-StrictMode -Version Latest

function Add-InstalledToolPaths {
    $packages = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    $links = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'
    $paths = @($links, (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313'))
    if (Test-Path -LiteralPath $packages) {
        $paths += @(Get-ChildItem "$packages\Gyan.FFmpeg_*\ffmpeg-*\bin" -Directory -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending | ForEach-Object FullName)
    }
    $paths += @($env:Path -split ';')
    $env:Path = (($paths | Where-Object { $_ } | Select-Object -Unique) -join ';')
}

function Find-Python313 {
    $known = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (Test-Path -LiteralPath $known) { return $known }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $resolved = & $launcher.Source -3.13 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath $resolved)) { return $resolved }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike '*\WindowsApps\*') {
        $ok = & $python.Source -c 'import sys; raise SystemExit(sys.version_info[:2] != (3,13))'
        if ($LASTEXITCODE -eq 0) { return $python.Source }
    }
    return $null
}
