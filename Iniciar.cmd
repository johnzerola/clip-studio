@echo off
setlocal
if exist "%~dp0Clip Studio.exe" (
    start "" "%~dp0Clip Studio.exe"
    if not errorlevel 1 exit /b 0
)
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\launch.ps1"
if errorlevel 1 pause
