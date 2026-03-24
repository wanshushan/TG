param(
    [ValidateSet("prod", "dev")]
    [string]$Mode = "prod",

    [ValidateSet("up", "down", "logs", "ps", "restart", "rebuild")]
    [string]$Action = "up",

    [switch]$Build,
    [switch]$Follow
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

function Invoke-Compose {
    param(
        [string[]]$ComposeArgs
    )

    Push-Location $projectRoot
    try {
        & docker compose @composeFiles @ComposeArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}

switch ($Action) {
    "up" {
        $cmdArgs = @("up", "-d")
        if ($Build) {
            $cmdArgs += "--build"
        }
        Invoke-Compose -ComposeArgs $cmdArgs
    }
    "down" {
        Invoke-Compose -ComposeArgs @("down")
    }
    "logs" {
        $cmdArgs = @("logs")
        if ($Follow) {
            $cmdArgs += "-f"
        }
        Invoke-Compose -ComposeArgs $cmdArgs
    }
    "ps" {
        Invoke-Compose -ComposeArgs @("ps")
    }
    "restart" {
        Invoke-Compose -ComposeArgs @("restart")
    }
    "rebuild" {
        Invoke-Compose -ComposeArgs @("up", "-d", "--build", "--force-recreate")
    }
}
