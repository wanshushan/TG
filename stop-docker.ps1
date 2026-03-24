param(
    [ValidateSet("prod", "dev")]
    [string]$Mode = "prod",

    [switch]$RemoveVolumes,
    [switch]$RemoveOrphans
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$prodCompose = Join-Path $projectRoot "docker-compose.yml"
$devCompose = Join-Path $projectRoot "docker-compose.dev.yml"

if (-not (Test-Path $prodCompose)) {
    throw "docker-compose.yml not found. Run this script from the project root."
}

if ($Mode -eq "dev" -and -not (Test-Path $devCompose)) {
    throw "docker-compose.dev.yml not found. Dev mode is unavailable."
}

$composeFiles = if ($Mode -eq "dev") {
    @("-f", $devCompose)
}
else {
    @("-f", $prodCompose)
}

$downArgs = @("down")
if ($RemoveVolumes) {
    $downArgs += "-v"
}
if ($RemoveOrphans) {
    $downArgs += "--remove-orphans"
}

Push-Location $projectRoot
try {
    & docker compose @composeFiles @downArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
