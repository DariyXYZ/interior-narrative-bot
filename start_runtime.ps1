$ErrorActionPreference = "Stop"

$scripts = @(
    "C:\VS Code\tools\bot-api-gateway\run_gateway.ps1",
    "C:\VS Code\tools\bot-api-gateway\run_ngrok.ps1",
    (Join-Path $PSScriptRoot "run_api.ps1"),
    (Join-Path $PSScriptRoot "run_bot.ps1")
)

foreach ($script in $scripts) {
    if (-not (Test-Path $script)) {
        throw "Missing runtime script: $script"
    }

    Start-Process powershell.exe `
        -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
        -WindowStyle Hidden
}
