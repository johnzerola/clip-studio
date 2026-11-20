@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute Instalar.cmd.
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 jobs_cli.py %*
exit /b %errorlevel%
