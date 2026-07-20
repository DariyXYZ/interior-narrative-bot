$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\ind_interior_bot", [ref]$created)
if (-not $created) {
    Write-Host "interior bot is already running"
    exit 0
}

while ($true) {
    if ((Test-Path "bot.err.log") -and ((Get-Item "bot.err.log").Length -gt 5MB)) {
        Move-Item -Force "bot.err.log" "bot.err.old.log"
    }
    python -m app.bot.main 2>> "bot.err.log"
    Start-Sleep -Seconds 5
}
