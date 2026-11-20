"""Control the shared Clip Studio job registry from a terminal."""
import argparse
import json
import os
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

from job_registry import ROOT, TERMINAL, cancel, finish, get, list_jobs, outputs, request_for, submit, tracked_session
from runtime_profile import PROFILES

STYLES = ("dynamic", "split", "reaction", "gamecam", "all")


def prepare(request):
    from editorial import Cleanup
    from engine import CAPTURE_HEIGHTS, Options, live_source
    from live_scout import ScoutSettings

    raw = request.get("sources")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 8 or any(not isinstance(item, str) for item in raw):
        raise ValueError("Informe uma lista de 1 a 8 fontes.")
    sources = []
    for value in dict.fromkeys(item.strip() for item in raw):
        path = Path(value)
        if "://" not in value and path.is_file():
            sources.append((str(path.resolve()), "file", []))
        else:
            url, vod = live_source(value)
            sources.append((url, "vod" if vod else "live", []))
    style = request.get("style", "dynamic")
    profile = request.get("performance", "leve")
    mode = request.get("mode", "render")
    duration = int(request.get("seconds", 45))
    count = int(request.get("count", 1))
    minutes = int(request.get("minutes", 5))
    threshold = int(request.get("threshold", 60))
    language = request.get("speech_language", "auto")
    capture_height = request.get("capture_height")
    replay_height = request.get("replay_height", 1440)
    if replay_height not in (1080, 1440):
        raise ValueError("Escolha replays em Full HD (1080p) ou 2K (1440p).")
    if capture_height is not None and capture_height not in CAPTURE_HEIGHTS:
        raise ValueError("Escolha captura em 480p, 720p ou 1080p.")
    modelar_reference = request.get("modelar_reference") or {}
    target_shot_seconds = float(modelar_reference.get("reference_shot_seconds", 3.0))
    poll_hours = int(request.get("live_poll_hours", 1))
    if poll_hours not in (0, 1, 2, 3):
        raise ValueError("Escolha uma frequência de 0, 1, 2 ou 3 horas.")
    if style not in STYLES or profile not in PROFILES or mode not in ("plan", "render"):
        raise ValueError("Modo, estilo ou perfil inválido.")
    if not (10 <= duration <= 180 and 1 <= count <= 8 and 0 <= minutes <= 720 and 20 <= threshold <= 95):
        raise ValueError("Duração 10–180 s, 1–8 clipes, captura 0–720 min e nota 20–95.")
    out = Path(request.get("output") or ROOT / "resultados").resolve()
    if out.exists() and not out.is_dir():
        raise ValueError("A saída precisa ser uma pasta.")
    from painel import parse_ranges
    manual = parse_ranges(request.get("ranges") or "")
    if manual and (len(sources) != 1 or sources[0][1] != "file"):
        raise ValueError("Cortes manuais precisam de um único arquivo local.")
    opts = Options(style, "", "", "direito", bool(request.get("captions", True)), False, duration, count,
                   mode == "render", manual=manual, cleanup=Cleanup(True, True, True, True, 1.2, -40),
                   auto_face=True, look="shorts", polish=True, voice_polish=True, jcut_ms=130,
                   transition="v9", compression="compacto", auto_music=bool(request.get("music", True)),
                   contextual_broll=False, keep_manual_edges=bool(manual), channel_handle=request.get("channel_handle") or "",
                   hook_text=request.get("hook_text") or "", effects_model=request.get("effects_model") or "",
                   smart_reframe=bool(request.get("smart_reframe", False)), speech_language=language,
                   target_shot_seconds=target_shot_seconds, full_hd=capture_height == 1080)
    scout = ScoutSettings(model=str(request.get("model") or ""), threshold=threshold, clip_seconds=duration,
                          review_final=bool(request.get("review", False)), continuous=minutes == 0,
                          catchup=bool(request.get("catchup", False)), performance=profile, live_poll_hours=poll_hours,
                          trim_inactive=bool(request.get("trim_inactive", True)),
                          transcribe_recordings=bool(request.get("transcribe_recordings", False)),
                          vision_model=str(request.get("vision_model") or ""), speech_language=language,
                          capture_height=capture_height, replay_after_live=bool(request.get("replay_after_live", False)),
                          replay_height=replay_height)
    return sources, opts, minutes, 1, out, 0, scout


def ensure_media_path():
    if os.name == "nt" and not shutil.which("ffmpeg"):
        packages = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        for binary in sorted(packages.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"), reverse=True):
            os.environ["PATH"] = str(binary.parent) + os.pathsep + os.environ.get("PATH", "")
            break


def run_pending(key):
    try:
        row = get(key)
        if row["state"] == "cancelled":
            return 0
        request = request_for(key)
        sources, opts, minutes, workers, output, wait, scout = prepare(request)
        ensure_media_path()
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        return tracked_session(row["origin"], sources, opts, minutes, workers, output, wait, stop,
                               lambda _line: None, scout, key=key)
    except Exception as error:
        if get(key)["state"] == "queued":
            finish(key, "failed", str(error)[:500])
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("submit", help="Iniciar um trabalho que aparece no painel")
    create.add_argument("sources", nargs="+")
    create.add_argument("--output", "--out")
    create.add_argument("--mode", choices=("plan", "render"), default="render")
    create.add_argument("--style", choices=STYLES, default="dynamic")
    create.add_argument("--performance", choices=tuple(PROFILES), default="leve")
    create.add_argument("--seconds", type=int, default=45)
    create.add_argument("--count", type=int, default=1)
    create.add_argument("--minutes", type=int, default=5)
    create.add_argument("--ranges", default="")
    create.add_argument("--model", default="")
    create.add_argument("--speech-language", choices=("auto", "pt", "en", "es"), default="auto")
    create.add_argument("--capture-height", type=int, choices=(480, 720, 1080))
    create.add_argument("--replay-after-live", action="store_true")
    create.add_argument("--replay-height", type=int, choices=(1080, 1440), default=1440)
    create.add_argument("--live-poll-hours", choices=(0,1,2,3), default=1, type=int)
    create.add_argument("--transcribe-recordings", action="store_true")
    create.add_argument("--vision-model", default="")
    create.add_argument("--keep-idle", dest="trim_inactive", action="store_false")
    create.add_argument("--threshold", type=int, default=60)
    create.add_argument("--review", action="store_true")
    create.add_argument("--catchup", action="store_true")
    create.add_argument("--channel-handle", default="", help="@ do seu canal no vídeo")
    create.add_argument("--hook-text", default="")
    create.add_argument("--effects-model", default="")
    create.add_argument("--smart-reframe", action="store_true")
    create.add_argument("--no-captions", dest="captions", action="store_false")
    create.add_argument("--no-music", dest="music", action="store_false")
    create.add_argument("--wait", action="store_true")
    sub.add_parser("list", help="Listar os trabalhos do painel, CLI e MCP")
    status = sub.add_parser("status", help="Consultar estado e eventos")
    status.add_argument("id")
    status.add_argument("--after", type=int, default=0)
    status.add_argument("--limit", type=int, default=50)
    for name in ("cancel", "outputs", "_run"):
        sub.add_parser(name).add_argument("id")
    args = parser.parse_args()
    try:
        if args.command == "_run":
            return run_pending(args.id)
        if args.command == "submit":
            request = vars(args).copy()
            wait = request.pop("wait")
            request.pop("command")
            result = submit(request, "CLI")
            if wait:
                while result["state"] not in TERMINAL:
                    time.sleep(1)
                    result = get(result["id"], limit=500)
        elif args.command == "list":
            result = list_jobs()
        elif args.command == "outputs":
            result = outputs(args.id)
        elif args.command == "status":
            result = get(args.id, after=args.after, limit=args.limit)
        else:
            result = cancel(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(args.command == "submit" and result["state"] in ("failed", "interrupted", "cancelled"))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
