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
    (Test-Path "$runtime/node.exe") -and (Test-Path "$runtime/web/server/index.mjs") -and
    (Test-Path "$runtime/director.mjs")) { return }
if ($Check) { throw 'Motor do painel ausente. Execute Instalar.cmd.' }
$sha = [Security.Cryptography.SHA256]::Create()
$stream = [IO.File]::OpenRead($archive)
try {
    $actual = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '')
} finally {
    $stream.Dispose()
    $sha.Dispose()
}
if ($actual -ne $expected) { throw 'O pacote do painel falhou na verificação SHA-256.' }
if (Test-Path $runtime) { throw 'O runtime existente precisa ser reparado em uma nova pasta de instalação.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $runtime)
if (-not ((Test-Path "$runtime/node.exe") -and (Test-Path "$runtime/web/server/index.mjs") -and
          (Test-Path "$runtime/director.mjs"))) { throw 'O pacote do painel esta incompleto.' }
[IO.File]::WriteAllText($stamp, $expected, [Text.Encoding]::ASCII)
Remove-Item -LiteralPath $archive -ErrorAction SilentlyContinue

