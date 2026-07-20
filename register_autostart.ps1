$ErrorActionPreference = "Stop"

$taskName = "IND Interior Runtime"
$runtimeScript = Join-Path $PSScriptRoot "start_runtime.ps1"
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runtimeScript`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "IND Telegram Mini App runtime" `
        -Force `
        -ErrorAction Stop | Out-Null
    Write-Host "Registered scheduled task: $taskName"
} catch {
    $startup = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startup "IND Interior Runtime.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = "IND Telegram Mini App runtime"
    $shortcut.Save()
    Write-Host "Task Scheduler is unavailable; Startup shortcut created: $shortcutPath"
}
