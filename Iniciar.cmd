@echo off
setlocal
cd /d "%~dp0"
set "runtime=%~dp0.venv\Scripts\python.exe"
if not exist "%runtime%" set "runtime=%~dp0..\live-clipper\.venv\Scripts\python.exe"
if not exist "%runtime%" (
  echo Execute Instalar.cmd primeiro.
  pause
  exit /b 1
)
"%runtime%" painel.py
if errorlevel 1 pause
