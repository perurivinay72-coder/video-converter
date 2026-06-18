# setup-task.ps1
# Run this script as Administrator to register the VideoConverter auto-watcher task
# Right-click PowerShell -> "Run as Administrator" -> run this script

$taskName   = "VideoConverter-AutoWatch"
$vbsPath    = "C:\Users\Vinay Peruri\video-converter\start-converter-silent.vbs"
$workDir    = "C:\Users\Vinay Peruri\video-converter"
$userName   = "Vinay Peruri"

$action   = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$vbsPath`"" `
    -WorkingDirectory $workDir

$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $userName

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)   # No time limit - runs forever

$principal = New-ScheduledTaskPrincipal `
    -UserId $userName `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName   $taskName `
    -Action     $action `
    -Trigger    $trigger `
    -Settings   $settings `
    -Principal  $principal `
    -Description "Watches inputs/ folder and auto-converts new videos to Markdown. Starts silently at Windows login." `
    -Force

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Task registered successfully!" -ForegroundColor Green
Write-Host "  Name   : $taskName" -ForegroundColor Cyan
Write-Host "  Trigger: At every login" -ForegroundColor Cyan
Write-Host "  Action : Silently starts the video converter watcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Starting the task now for the first time..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $taskName
Write-Host "Done! The watcher is now running in the background." -ForegroundColor Green
