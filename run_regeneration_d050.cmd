@echo off
rem Partial regeneration after D-048 / D-049 / D-050 (crank). Logs: regen_logs_d050\  Console: regen_logs_d050_console.log
cd /d "%~dp0"
set PYTHONPATH=src
.venv\Scripts\python.exe tools\regenerate_d050.py > regen_logs_d050_console.log 2>&1
type regen_logs_d050_console.log
