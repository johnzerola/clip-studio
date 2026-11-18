"""Entrada de automação para mídia já disponível no disco."""
import argparse
from pathlib import Path

from engine import Options, crop, process
from painel import parse_ranges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="Pasta nova de resultados")
    parser.add_argument("--style", choices=["dynamic", "split", "reaction"], default="dynamic")
    parser.add_argument("--face", default="")
    parser.add_argument("--game", default="")
    parser.add_argument("--corner", choices=["direito", "esquerdo"], default="direito")
    parser.add_argument("--duration", type=int, default=90)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--ranges", default="")
    parser.add_argument("--contiguous", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--captions", action="store_true")
    args = parser.parse_args()
    if not args.source.is_file() or args.out.exists():
        parser.error("Informe um arquivo existente e uma pasta de saída nova.")
    if not 10 <= args.duration <= 180 or not 1 <= args.count <= 8:
        parser.error("Duração entre 10 e 180 s e quantidade entre 1 e 8.")
    try:
        crop(args.face)
        crop(args.game)
        manual = parse_ranges(args.ranges)
        opts = Options(args.style, args.face, args.game, args.corner, args.captions,
                       not args.contiguous, args.duration, args.count, args.render, manual)
        process(args.source, args.out.resolve(), opts, print)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
