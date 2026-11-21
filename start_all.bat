@echo off
cd /d "%~dp0"
set PY=%~dp0.venv\Scripts\python.exe
start "" "%PY%" -m ui.watchdog_runner
start "" "%PY%" -m ui.autonomous_scheduler
start "" "%PY%" -m ui.tr_runner
exit /b 0
