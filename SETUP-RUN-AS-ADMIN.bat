@echo off
echo ================================================
echo   VideoConverter - Task Scheduler Setup
echo   Run this as Administrator!
echo ================================================
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0setup-task.ps1"
echo.
pause
