@echo off
REM One-click launcher for CodeABC on Windows. Just double-click this file.
cd /d "%~dp0"
python run.py
if errorlevel 1 py run.py
echo.
pause
