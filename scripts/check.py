"""Read-only diagnostics for the Windows installer."""
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for name in ("tkinter", "faster_whisper", "cv2", "numpy", "yt_dlp", "streamlink",
             "truststore", "opentimelineio", "ffpyplayer.player", "painel", "sessions", "posting_panel"):
    importlib.import_module(name)

for name in ("ffmpeg", "ffprobe"):
    if not shutil.which(name):
        raise SystemExit(f"{name} não encontrado.")
    subprocess.run([name, "-version"], stdout=subprocess.DEVNULL, check=True)
filters = subprocess.check_output(["ffmpeg", "-hide_banner", "-filters"], text=True, errors="replace")
encoders = subprocess.check_output(["ffmpeg", "-hide_banner", "-encoders"], text=True, errors="replace")
if " ass " not in filters or not any(name in encoders for name in ("libx264", "libopenh264")):
    raise SystemExit("FFmpeg precisa de libass e um encoder H.264. Instale a compilação Gyan.FFmpeg.")
print(f"Python {sys.version.split()[0]}, FFmpeg, FFprobe, Tk, captura e edição disponíveis.")
print("Ollama:", "CLI encontrada" if shutil.which("ollama") else "opcional, ausente")
