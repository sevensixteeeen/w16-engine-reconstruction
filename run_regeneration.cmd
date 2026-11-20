@echo off
rem Full regeneration on D-041 / D-042 (no piston FE). Logs: regen_logs\  Console: regen_logs_console.log
cd /d "%~dp0"
set PYTHONPATH=src
.venv\Scripts\python.exe tools\regenerate_d042.py > regen_logs_console.log 2>&1
type regen_logs_console.log
