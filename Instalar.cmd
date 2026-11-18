@echo off
setlocal
cd /d "%~dp0"
where ffmpeg >nul 2>&1 && where ffprobe >nul 2>&1
if errorlevel 1 (
  echo Instale FFmpeg com FFprobe e adicione ao PATH.
  echo No Windows, uma opcao e: winget install Gyan.FFmpeg
  goto error
)
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Instalado. Abra Iniciar.cmd.
pause
exit /b 0
:error
echo Falha na instalacao. Confira a mensagem acima.
pause
exit /b 1
