@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -m ui.watchdog_runner >nul 2>&1
exit /b 0
