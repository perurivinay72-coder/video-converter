@echo off
REM Auto-Converter batch file for Windows
REM Usage: run-converter.bat [--once]
REM   --once = Process existing files and exit (no watching)
REM   (default) = Watch folder for new files

cd /d "%~dp0"
"C:\Users\Vinay Peruri\AppData\Local\Programs\Python\Python312\python.exe" "auto converter.py" %*
