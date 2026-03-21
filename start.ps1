$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$rdPath = Join-Path $projectRoot "RD"
$fePath = Join-Path $projectRoot "FE"

Start-Process pwsh -ArgumentList "-NoExit", "-Command", "Set-Location '$rdPath'; python main.py"
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "Set-Location '$fePath'; pnpm run preview"
