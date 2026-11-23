"""Download an audio-only replay for analysis and video only for selected intervals."""
import json
import subprocess
import sys
import time

import runtime_profile as runtime


def download(url, directory, kind, stop, *, window=None, limit=None, max_height=1440):
    from compression import metadata
    from engine import REPLAY_HEIGHTS, capture_space, command

    directory.mkdir(parents=True, exist_ok=True)
    suffix = "opus" if kind == "audio" else "mp4"
    target = directory / f"{kind}.{suffix}"
    args = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--compat-options", "no-certifi",
            "--no-playlist", "--match-filter", "!is_live & !is_upcoming", "--socket-timeout", "15",
            "--retries", "2", "--concurrent-fragments", "1", "--no-progress"]
    if kind == "audio":
        args += ["-f", "bestaudio/best", "--extract-audio", "--audio-format", "opus"]
    elif kind in ("video", "preview") and window is not None:
        start, end = window
        if not 0 <= start < end <= start + 181:
            raise ValueError("Intervalo de vídeo inválido.")
        allowed = (480,) if kind == "preview" else REPLAY_HEIGHTS
        if max_height not in allowed:
            raise ValueError("Qualidade de replay deve ser Full HD, 2K ou 4K.")
        args += ["-f", f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/bestvideo[height<={max_height}]",
                 "-S", f"res:{max_height}",
                 "--download-sections", f"*{start:.3f}-{end:.3f}",
                 "--merge-output-format", "mp4", "--remux-video", "mp4"]
    else:
        raise ValueError("Vídeo de replay exige um intervalo selecionado.")
    args += ["-o", str(target), "--", url]
    if stop.is_set():
        raise InterruptedError("Download cancelado.")
    log_path = directory.parent / "download.log"
    with log_path.open("ab") as log:
        log_start = log.tell()
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
                    with log_path.open("rb") as reader:
                        reader.seek(max(log_start, log_path.stat().st_size - 8192))
                        lines = reader.read().decode("utf-8", "replace").splitlines()
                    error = next((line.removeprefix("ERROR: ") for line in reversed(lines) if line.startswith("ERROR: ")), "")
                    raise RuntimeError(f"{detail}. {error[:320] or 'Consulte download.log.'}")
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


def replay_duration(url):
    from engine import command

    data = json.loads(command([sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                               "--skip-download", "--dump-single-json", "--socket-timeout", "12", "--", url],
                              timeout=35))
    if data.get("is_live") or data.get("live_status") in {"is_live", "is_upcoming"}:
        raise ValueError("A transmissão ainda não virou replay.")
    duration = float(data.get("duration") or 0.)
    if not 8 <= duration <= 7 * 86400:
        raise ValueError("Duração da gravação indisponível.")
    return duration


def gameplay_candidates(url, folder, stop, total, options, log):
    """Probe at most three short low-resolution samples from a speechless VOD."""
    from tempfile import TemporaryDirectory
    from engine import inspect, probe

    length = min(20., total, options.duration)
    starts = sorted(set(round(max(0., total - length) * point, 3) for point in (.18, .50, .82)))
    picks = []
    for start in starts:
        if stop.is_set():
            raise InterruptedError("Triagem cancelada.")
        end = start + length
        try:
            with TemporaryDirectory(prefix="replay-amostra-", dir=folder) as scratch:
                from pathlib import Path
                sample, _ = download(url, Path(scratch), "preview", stop, window=(start, end),
                                     limit=80 * 1024**2, max_height=480)
                duration, audio = probe(sample)
                motions = [motion for _, motion, _ in inspect(sample, duration, audio)]
                motion = max(motions, default=0.)
                if motion >= 1.35:
                    picks.append({"start": start, "end": round(end, 3), "transcript": "",
                                  "av_score": min(65, round(36 + 10 * motion)),
                                  "features": {"motion": round(motion, 2), "selection_source": "gameplay_amostrado"}})
        except InterruptedError:
            raise
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            log("Amostra visual do replay indisponível. Verificando o próximo trecho.")
    return sorted(picks, key=lambda pick: -pick["av_score"])[:options.count]
