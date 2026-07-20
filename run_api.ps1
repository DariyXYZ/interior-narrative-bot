$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\ind_interior_api", [ref]$created)
if (-not $created) {
    Write-Host "interior API is already running"
    exit 0
}

while ($true) {
    if ((Test-Path "api.err.log") -and ((Get-Item "api.err.log").Length -gt 5MB)) {
        Move-Item -Force "api.err.log" "api.err.old.log"
    }
    python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8010 2>> "api.err.log"
    Start-Sleep -Seconds 5
}
