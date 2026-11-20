"""Download an audio-only replay for analysis and video only for selected intervals."""
import json
import subprocess
import sys
import time

import runtime_profile as runtime


def download(url, directory, kind, stop, *, window=None, limit=None, max_height=1440):
    from compression import metadata
    from engine import capture_space, command

    directory.mkdir(parents=True, exist_ok=True)
    suffix = "mp4" if kind == "video" else "mka"
    target = directory / f"{kind}.{suffix}"
    args = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--compat-options", "no-certifi",
            "--no-playlist", "--match-filter", "!is_live & !is_upcoming", "--socket-timeout", "15",
            "--retries", "2", "--concurrent-fragments", "1", "--no-progress"]
    if kind == "audio":
        args += ["-f", "bestaudio", "--remux-video", "mka"]
    elif kind == "video" and window is not None:
        start, end = window
        if not 0 <= start < end <= start + 181:
            raise ValueError("Intervalo de vídeo inválido.")
        if max_height not in (1080, 1440):
            raise ValueError("Qualidade de replay deve ser Full HD ou 2K.")
        args += ["-f", f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]",
                 "-S", f"res:{max_height}",
                 "--download-sections", f"*{start:.3f}-{end:.3f}",
                 "--merge-output-format", "mp4", "--remux-video", "mp4"]
    else:
        raise ValueError("Vídeo de replay exige um intervalo selecionado.")
    args += ["-o", str(target), "--", url]
    if stop.is_set():
        raise InterruptedError("Download cancelado.")
    with (directory.parent / "download.log").open("ab") as log:
        with subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                              **runtime.child_options(force_low=True, hide=True)) as child:
            deadline = time.monotonic() + (1800 if window else 21600)
            try:
                while child.poll() is None:
                    if stop.is_set():
                        raise InterruptedError("Download cancelado.")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Prazo para baixar mídia atingido.")
                    if not capture_space(directory):
                        raise OSError("Download interrompido para preservar espaço em disco.")
                    saved = 0
                    for file in directory.iterdir():
                        try:
                            saved += file.stat().st_size
                        except FileNotFoundError:
                            pass
                    if limit and saved > limit:
                        raise OSError("Download ultrapassou o limite de armazenamento.")
                    stop.wait(.5)
                if child.returncode or not target.is_file():
                    detail = "O provedor não entregou uma faixa de áudio separada" if kind == "audio" else "O provedor não entregou o intervalo"
                    raise RuntimeError(f"{detail}. Consulte {directory.parent / 'download.log'}.")
            finally:
                if child.poll() is None:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                       capture_output=True, **runtime.child_options(hide=True))
                    child.kill()
                    child.wait()
    if limit and target.stat().st_size > limit:
        raise OSError("Download ultrapassou o limite de armazenamento.")
    if window:
        _, _, (width, height, _), duration = metadata(target)
        if abs(duration - (end - start)) > 2.5:
            raise RuntimeError("O vídeo recebido não corresponde à duração do intervalo.")
        return target, (width, height)
    info = json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                               "-of", "json", str(target)], timeout=20))
    duration = float(info["format"].get("duration") or 0)
    tracks = {stream["codec_type"] for stream in info["streams"]}
    if tracks != {"audio"} or duration <= 0:
        raise RuntimeError("A faixa de áudio está indisponível.")
    return target, duration
