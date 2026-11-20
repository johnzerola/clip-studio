"""Monitor saved channels and export only clips approved after editing."""
import argparse
import signal
import threading
from pathlib import Path

from editorial import Cleanup
from engine import Options, live_source
from live_scout import ScoutSettings
from job_registry import tracked_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channels", nargs="*", help="Canais/URLs, ou use --channels-file")
    parser.add_argument("--channels-file", type=Path, help="Um canal por linha")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--vision-model", default="")
    parser.add_argument("--keep-idle", action="store_true")
    parser.add_argument("--threshold", type=int, default=60)
    parser.add_argument("--clip-seconds", type=int, default=45)
    parser.add_argument("--minutes", type=int, default=0, help="0 monitora continuamente")
    parser.add_argument("--no-catchup", action="store_true")
    parser.add_argument("--recent", type=int, choices=(0, 2, 3), default=0)
    parser.add_argument("--replay-hours", type=int, choices=(0, 1, 2, 3), default=0)
    parser.add_argument("--live-poll-hours", type=int, choices=(0, 1, 2, 3), default=0)
    parser.add_argument("--replay-only", action="store_true")
    parser.add_argument("--replay-gib", type=int, default=12)
    parser.add_argument("--performance", choices=("leve", "equilibrado"), default="leve")
    args = parser.parse_args()
    try:
        lines = args.channels + (args.channels_file.read_text(encoding="utf-8-sig").splitlines() if args.channels_file else [])
        normalized = dict.fromkeys(live_source(line.strip()) for line in lines if line.strip() and not line.lstrip().startswith("#"))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if not 1 <= len(normalized) <= 8 or any(vod for _, vod in normalized):
        parser.error("Use de 1 a 8 canais ou URLs de live.")
    if not (20 <= args.threshold <= 95 and 10 <= args.clip_seconds <= 180 and 0 <= args.minutes <= 720):
        parser.error("Revise nota mínima, duração do corte e tempo de captura.")
    if (args.replay_only or args.replay_hours) and not args.recent:
        parser.error("Use --recent 2 ou --recent 3.")
    if args.recent:
        from replay_library import archive_url
        try:
            for url, _ in normalized:
                archive_url(url)
        except ValueError as error:
            parser.error(str(error))
    if args.replay_gib < 1:
        parser.error("Use um limite positivo para o replay.")
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda _sig, _frame: stop.set())
    cleanup = Cleanup(True, True, True, True, 1.2, -40, speech_gaps=True)
    edit = Options("dynamic", "", "", "direito", True, False, args.clip_seconds, 1, True,
                   cleanup=cleanup, auto_face=True, look="shorts", hook=True, polish=True,
                   voice_polish=True, jcut_ms=130, transition="v9", compression="compacto", save_review=False)
    scout = ScoutSettings(model=args.model, threshold=args.threshold, clip_seconds=args.clip_seconds,
                          review_final=True, continuous=args.minutes == 0, catchup=not args.no_catchup,
                          replay_count=args.recent, replay_period=args.replay_hours, replay_only=args.replay_only,
                          replay_gib=args.replay_gib, live_poll_hours=args.live_poll_hours, performance=args.performance,
                          trim_inactive=not args.keep_idle, vision_model=args.vision_model)
    try:
        return tracked_session("CLI", [(url, "live", []) for url, _ in normalized], edit, args.minutes, 1,
                               args.out.resolve(), 15, stop, lambda line: print(line, flush=True), scout)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
