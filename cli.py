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
    parser.add_argument("--polish", action="store_true", help="Adiciona transições visuais e sons discretos")
    parser.add_argument("--broll-dir", default="", help="Pasta de mídia autorizada nomeada pela palavra de entrada")
    parser.add_argument("--close-focus", type=float, default=.5, help="Posição horizontal do close, de 0 a 1")
    parser.add_argument("--voice-polish", action="store_true")
    parser.add_argument("--jcut-ms", type=int, default=0)
    parser.add_argument("--music", default="")
    parser.add_argument("--music-db", type=int, default=-25)
    parser.add_argument("--transition", choices=["corte", "linha", "zoom", "v9"], default="zoom")
    parser.add_argument("--sfx", choices=["auto", "whoosh", "radio", "impacto", "resolucao", "nenhum"], default="auto")
    parser.add_argument("--sfx-peak", type=int, default=-8)
    parser.add_argument("--game", default="")
    parser.add_argument("--corner", choices=["direito", "esquerdo"], default="direito")
    parser.add_argument("--duration", type=int, default=90)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--ranges", default="")
    parser.add_argument("--contiguous", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--compression", choices=("original", "compacto", "hevc"), default="compacto")
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
    if not 0 <= args.close_focus <= 1 or (args.broll_dir and not Path(args.broll_dir).is_dir()):
        parser.error("Use centro do close entre 0 e 1 e uma pasta de B-roll existente.")
    if not 0 <= args.jcut_ms <= 250 or not -45 <= args.music_db <= -12:
        parser.error("J-cut entre 0 e 250 ms e trilha entre -45 e -12 dB.")
    if args.music and not Path(args.music).is_file():
        parser.error("A faixa musical não existe.")
    if not -24 <= args.sfx_peak <= -3:
        parser.error("Pico dos efeitos entre -24 e -3 dBFS.")
    try:
        crop(args.face)
        crop(args.game)
        manual = parse_ranges(args.ranges)
        cleanup = Cleanup(args.cut_silence, args.cut_repeats, args.cut_fillers, args.link_speech,
                          args.min_pause, args.silence_db, speech_gaps=args.cut_speech_gaps)
        opts = Options(args.style, args.face, args.game, args.corner, args.captions,
                       not args.contiguous, args.duration, args.count, args.render, manual, cleanup, args.auto_face,
                       args.look, args.hook, args.polish, args.broll_dir, args.close_focus,
                       args.voice_polish, args.jcut_ms, args.music, args.music_db,
                       args.transition, args.sfx, args.sfx_peak, args.compression)
        process(args.source, args.out.resolve(), opts, print)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
