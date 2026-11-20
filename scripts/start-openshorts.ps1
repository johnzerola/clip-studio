param([switch]$Validate)
$ErrorActionPreference = 'Stop'
$reference = Join-Path $PSScriptRoot '..\work\openshorts-reference'
if (!(Test-Path -LiteralPath (Join-Path $reference 'Dockerfile'))) {
    throw 'Clone https://github.com/mutonby/openshorts em work/openshorts-reference.'
}
$project = (Resolve-Path -LiteralPath $reference).Path
$compose = Join-Path $PSScriptRoot 'openshorts-ugc.yml'
if ($Validate) {
    docker compose --project-directory $project -f $compose config --quiet
} else {
    docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw 'Abra o Docker Desktop e espere o motor Linux ficar pronto.' }
    docker compose --project-directory $project -f $compose up -d --build
}
exit $LASTEXITCODE
