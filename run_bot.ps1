$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\ind_interior_bot", [ref]$created)
if (-not $created) {
    Write-Host "interior bot is already running"
    exit 0
}

# Осиротевший child предыдущей обёртки = второй polling-инстанс и Telegram Conflict — убираем.
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.bot\.main' -and $_.Name -eq 'python.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

while ($true) {
    if ((Test-Path "bot.err.log") -and ((Get-Item "bot.err.log").Length -gt 5MB)) {
        Move-Item -Force "bot.err.log" "bot.err.old.log"
    }
    # cmd /c: байтовый redirect без PowerShell ErrorRecord/UTF-16 обёртки
    cmd /c "python -m app.bot.main 2>> bot.err.log"
    Start-Sleep -Seconds 5
}
