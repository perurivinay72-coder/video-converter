@echo off
REM MarkItDown Auto-Converter (Whisper Edition)
REM ============================================
REM USAGE:
REM   run-converter.bat           -> Watch mode: stays alive, converts new files automatically
REM   run-converter.bat --once    -> One-shot: convert existing files and exit
REM   run-converter.bat --model small  -> Use a larger Whisper model (more accurate, slower)

cd /d "%~dp0"
echo Starting MarkItDown Auto-Converter (Whisper Edition)...
echo Drop videos/audio into the "inputs" folder and they will auto-convert to Markdown.
echo Press Ctrl+C to stop the watcher.
echo.
"C:\Users\Vinay Peruri\AppData\Local\Programs\Python\Python312\python.exe" "auto converter.py" %*
pause
