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
from engine import CAPTURE_HEIGHTS, REPLAY_HEIGHTS

STYLES = ("dynamic", "split", "reaction", "gamecam", "all", "interview")


def prepare(request):
    from broll_library import configured_visuals
    from editorial import Cleanup
    from engine import Options, live_source
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
    acceleration = request.get("acceleration", "auto")
    if acceleration not in ("auto", "cpu"):
        raise ValueError("Escolha aceleração automática ou CPU.")
    duration = int(request.get("seconds", 45))
    count = int(request.get("count", 1))
    minutes = int(request.get("minutes", 5))
    threshold = int(request.get("threshold", 60))
    language = request.get("speech_language", "auto")
    capture_height = request.get("capture_height")
    replay_height = request.get("replay_height", 1440)
    if replay_height not in REPLAY_HEIGHTS:
        raise ValueError("Escolha replays em Full HD (1080p), 2K (1440p) ou 4K (2160p).")
    if capture_height is not None and capture_height not in CAPTURE_HEIGHTS:
        raise ValueError("Escolha captura em 480p, 720p, 1080p, 1440p ou 2160p.")
    modelar_reference = request.get("modelar_reference") or {}
    kit_mode = request.get("live_kit_mode", "on" if request.get("gta_kit_style") is True else "off")
    if kit_mode not in ("auto", "on", "off"):
        raise ValueError("Escolha o estilo de gameplay automático, sempre ou desligado.")
    target_shot_seconds = float(modelar_reference.get("reference_shot_seconds", 3.0))
    poll_hours = int(request.get("live_poll_hours", 1))
    if poll_hours not in (0, 1, 2, 3):
        raise ValueError("Escolha uma frequência de 0, 1, 2 ou 3 horas.")
    replay_count = int(request.get("replay_count", 0))
    replay_period = int(request.get("replay_period", 0))
    replay_gib = int(request.get("replay_gib", 12))
    replay_only = bool(request.get("replay_only", False))
    if replay_count not in (0, 2, 3) or replay_period not in (0, 1, 2, 3) or not 1 <= replay_gib <= 100:
        raise ValueError("Escolha 2 ou 3 replays, frequência de 1 a 3 horas e limite de 1 a 100 GiB.")
    if (replay_only or replay_period) and not replay_count:
        raise ValueError("Selecione quantas gravações procurar.")
    if replay_count:
        from replay_library import archive_url
        if any(kind != "live" for _, kind, _ in sources):
            raise ValueError("Para buscar replays, informe apenas links de canais.")
        for url, _, _ in sources:
            archive_url(url)
    if style not in STYLES or profile not in PROFILES or mode not in ("plan", "render", "preview"):
        raise ValueError("Modo, estilo ou perfil inválido.")
    if not (10 <= duration <= 180 and 1 <= count <= 8 and 0 <= minutes <= 720 and 20 <= threshold <= 95):
        raise ValueError("Duração 10–180 s, 1–8 clipes, captura 0–720 min e nota 20–95.")
    out = Path(request.get("output") or ROOT / "resultados").resolve()
    if out.exists() and not out.is_dir():
        raise ValueError("A saída precisa ser uma pasta.")
    from painel import parse_ranges
    manual = parse_ranges(request.get("ranges") or "")
    if mode == "preview" and any(kind != "file" for _, kind, _ in sources):
        raise ValueError("A prévia de inserções usa arquivos de vídeo locais.")
    if manual and (len(sources) != 1 or sources[0][1] != "file"):
        raise ValueError("Cortes manuais precisam de um único arquivo local.")
    library, background, backdrop = configured_visuals(ROOT, request)
    opts = Options(style, "", "", "direito", bool(request.get("captions", True)), False, duration, count,
                   mode != "plan", manual=manual, cleanup=Cleanup(True, True, True, True, 1.2, -40),
                   auto_face=True, look="shorts", live_kit_mode=kit_mode, polish=True, voice_polish=True, jcut_ms=130,
                   transition="v9", compression="compacto", auto_music=bool(request.get("music", True)),
                   contextual_broll=False, keep_manual_edges=bool(manual), channel_handle=request.get("channel_handle") or "",
                   hook_text=request.get("hook_text") or "", effects_model=request.get("effects_model") or "",
                   smart_reframe=bool(request.get("smart_reframe", False)), speech_language=language,
                   target_shot_seconds=target_shot_seconds, full_hd=bool(capture_height and capture_height >= 1080),
                   director_reference={key: modelar_reference[key] for key in ("preset_sha256", "analysis_id", "reference_shot_seconds", "source_hashes")
                                       if key in modelar_reference} or None,
                   precompress=bool(request.get("precompress", True)), visual_library=library,
                   visual_background=background, background_asset=backdrop, review_visuals=mode == "preview")
    auto_finalize = bool(request.get("auto_finalize", False)) and mode == "render"
    scout = ScoutSettings(model=str(request.get("model") or ""), threshold=threshold, clip_seconds=duration,
                          review_final=auto_finalize or bool(request.get("review", False)), continuous=minutes == 0,
                          catchup=bool(request.get("catchup", False)), performance=profile, live_poll_hours=poll_hours,
                          replay_count=replay_count, replay_period=replay_period, replay_only=replay_only, replay_gib=replay_gib,
                          trim_inactive=bool(request.get("trim_inactive", True)),
                          transcribe_recordings=bool(request.get("transcribe_recordings", False)),
                          vision_model=str(request.get("vision_model") or ""), speech_language=language,
                          capture_height=capture_height, replay_after_live=bool(request.get("replay_after_live", False)),
                          replay_height=replay_height, acceleration=acceleration, auto_finalize=auto_finalize)
    return sources, opts, minutes, 1, out, 0, scout


def ensure_media_path():
    if os.name == "nt" and not shutil.which("ffmpeg"):
        packages = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        for package in ("Gyan.FFmpeg_*", "BtbN.FFmpeg.*"):
            for binary in sorted(packages.glob(f"{package}/ffmpeg-*/bin/ffmpeg.exe"), reverse=True):
                if binary.with_name("ffprobe.exe").is_file():
                    os.environ["PATH"] = str(binary.parent) + os.pathsep + os.environ.get("PATH", "")
                    return


def run_pending(key):
    try:
        row = get(key)
        if row["state"] == "cancelled":
            return 0
        request = request_for(key)
        ensure_media_path()
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        if request.get("gta_kit"):
            from gta_kit import render
            from job_registry import start
            return start(key, lambda event, session: render(request, event, session, stop), stop, lambda _line: None)
        if request.get("visual_review"):
            from job_registry import start
            from visual_review import run_review
            return start(key, lambda event, session: run_review(request, event, session, stop), stop, lambda _line: None)
        sources, opts, minutes, workers, output, wait, scout = prepare(request)
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
    create.add_argument("--mode", choices=("plan", "render", "preview"), default="render")
    create.add_argument("--style", choices=STYLES, default="dynamic")
    create.add_argument("--performance", choices=tuple(PROFILES), default="leve")
    create.add_argument("--acceleration", choices=("auto", "cpu"), default="auto")
    create.add_argument("--no-precompress", dest="precompress", action="store_false")
    create.add_argument("--seconds", type=int, default=45)
    create.add_argument("--count", type=int, default=1)
    create.add_argument("--minutes", type=int, default=5)
    create.add_argument("--ranges", default="")
    create.add_argument("--model", default="")
    create.add_argument("--speech-language", choices=("auto", "pt", "en", "es"), default="auto")
    create.add_argument("--capture-height", type=int, choices=CAPTURE_HEIGHTS)
    create.add_argument("--replay-after-live", action="store_true")
    create.add_argument("--auto-finalize", action="store_true",
                        help="Revisar com IA, tentar um ajuste e preservar até três candidatos da live para revisão manual.")
    create.add_argument("--replay-height", type=int, choices=REPLAY_HEIGHTS, default=1440)
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
