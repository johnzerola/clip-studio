"""Entrada de automação para mídia já disponível no disco."""
import argparse
from pathlib import Path

from engine import Options, crop, process
from editorial import Cleanup
from painel import parse_ranges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="Pasta nova de resultados")
    parser.add_argument("--style", choices=["dynamic", "split", "reaction", "gamecam", "all"], default="dynamic")
    parser.add_argument("--face", default="")
    parser.add_argument("--auto-face", action="store_true")
    parser.add_argument("--look", choices=["classic", "shorts"], default="classic")
    parser.add_argument("--hook", action="store_true")
    parser.add_argument("--game", default="")
    parser.add_argument("--corner", choices=["direito", "esquerdo"], default="direito")
    parser.add_argument("--duration", type=int, default=90)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--ranges", default="")
    parser.add_argument("--contiguous", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--captions", action="store_true")
    parser.add_argument("--cut-silence", action="store_true")
    parser.add_argument("--cut-repeats", action="store_true")
    parser.add_argument("--cut-fillers", action="store_true")
    parser.add_argument("--link-speech", action="store_true")
    parser.add_argument("--cut-speech-gaps", action="store_true")
    parser.add_argument("--min-pause", type=float, default=.9)
    parser.add_argument("--silence-db", type=int, default=-36)
    args = parser.parse_args()
    if not args.source.is_file() or args.out.exists():
        parser.error("Informe um arquivo existente e uma pasta de saída nova.")
    if not 10 <= args.duration <= 180 or not 1 <= args.count <= 8:
        parser.error("Duração entre 10 e 180 s e quantidade entre 1 e 8.")
    if not (.3 <= args.min_pause <= 5 and -65 <= args.silence_db <= -18):
        parser.error("Use pausa entre 0,3 e 5 s e limiar entre -65 e -18 dBFS.")
    try:
        crop(args.face)
        crop(args.game)
        manual = parse_ranges(args.ranges)
        cleanup = Cleanup(args.cut_silence, args.cut_repeats, args.cut_fillers, args.link_speech,
                          args.min_pause, args.silence_db, speech_gaps=args.cut_speech_gaps)
        opts = Options(args.style, args.face, args.game, args.corner, args.captions,
                       not args.contiguous, args.duration, args.count, args.render, manual, cleanup, args.auto_face,
                       args.look, args.hook)
        process(args.source, args.out.resolve(), opts, print)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
