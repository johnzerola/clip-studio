@echo off
setlocal
cd /d "%~dp0"
if /I "%~1"=="--automatico" goto automatico
if /I "%~1"=="--verificar" goto verificar
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\install.ps1"
if errorlevel 1 goto erro
pause
exit /b 0
:automatico
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\install.ps1" -InstallPrerequisites
exit /b %errorlevel%
:verificar
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\install.ps1" -Check
exit /b %errorlevel%
:erro
echo Use Instalar.cmd --automatico para instalar pre-requisitos que estiverem faltando.
pause
exit /b 1
