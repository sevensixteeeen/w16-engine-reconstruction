@echo off
rem D-050 correction (2026-11-27): crank FE stage, then the R2.5 convergence (about 5 h). Nothing else open.
rem Logs: regen_logs_d050_fix\  Console: regen_logs_d050_fix_console.log
cd /d "%~dp0"
set PYTHONPATH=src
.venv\Scripts\python.exe tools\regenerate_d050_fix.py > regen_logs_d050_fix_console.log 2>&1
type regen_logs_d050_fix_console.log
