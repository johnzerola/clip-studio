param([switch]$Check)
$ErrorActionPreference = 'Stop'
$base = (Resolve-Path $PSScriptRoot).Path
$archive = Join-Path $base 'runtime.zip'
$runtime = Join-Path $base 'runtime'
$manifest = Join-Path $base 'runtime.sha256'
if (-not (Test-Path $archive) -and -not (Test-Path $manifest)) { return }
$expected = (Get-Content -LiteralPath $manifest -Raw).Trim()
$stamp = Join-Path $runtime '.installed'
if ((Test-Path $stamp) -and (Get-Content $stamp -Raw).Trim() -eq $expected -and
    (Test-Path "$runtime/node.exe") -and (Test-Path "$runtime/web/server/index.mjs")) { return }
if ($Check) { throw 'Motor do painel ausente. Execute Instalar.cmd.' }
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'O pacote do painel falhou na verificação SHA-256.' }
$stage = Join-Path $base ('runtime-' + [Guid]::NewGuid())
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $stage)
Set-Content -LiteralPath (Join-Path $stage '.installed') -Value $expected -Encoding ascii
if (Test-Path $runtime) { throw 'O runtime existente precisa ser reparado em uma nova pasta de instalação.' }
[IO.Directory]::Move($stage, $runtime)

