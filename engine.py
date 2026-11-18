"""Local ingestion, highlight selection and vertical rendering."""
import array
import csv
import json
import math
import re
import statistics
import subprocess as sp
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

WIDTH, HEIGHT = 720, 1280
FF = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
ENC = ["-pix_fmt", "yuv420p",
       "-c:a", "aac", "-ar", "48000", "-ac", "2", "-threads", "2"]
MODEL_LOCK = threading.Lock()
MODELS = {}


@dataclass(frozen=True)
class Options:
    style: str
    face: str
    game: str
    corner: str
    captions: bool
    montage: bool
    duration: int
    count: int
    render: bool
    manual: tuple = ()


def command(args, **kwargs):
    result = sp.run(args, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip()[-900:] or str(args[0]))
    return result.stdout


@lru_cache(maxsize=1)
def encoder():
    available = command(FF + ["-encoders"]).decode("utf-8", "replace")
    if re.search(r"\blibx264\b", available):
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"]
    if re.search(r"\blibopenh264\b", available):
        return ["-c:v", "libopenh264", "-b:v", "4M"]
    raise RuntimeError("O FFmpeg precisa do encoder libx264 ou libopenh264.")


def probe(source):
    data = json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                               "-of", "json", str(source)]))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("Fonte sem vídeo.")
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duração da fonte indisponível.")
    return duration, any(s["codec_type"] == "audio" for s in data["streams"])


def inspect(source, duration, audio):
    """Two-second samples. No rendering or speech model needed for this pass."""
    pcm = array.array("h")
    if audio:
        pcm.frombytes(command(FF + ["-threads", "2", "-i", str(source), "-vn", "-ac", "1",
                                    "-ar", "800", "-f", "s16le", "pipe:1"]))
    frames = command(FF + ["-threads", "2", "-filter_threads", "1", "-i", str(source),
                          "-an", "-vf", "fps=1/2,scale=32:18,format=gray",
                          "-c:v", "rawvideo", "-threads", "1", "-f", "rawvideo", "pipe:1"])
    pairs = []
    for i in range(math.ceil(duration / 2)):
        samples = pcm[i * 1600:(i + 1) * 1600]
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0
        current = frames[i * 576:(i + 1) * 576]
        prior = frames[(i - 1) * 576:i * 576] if i else b""
        motion = sum(abs(a - b) for a, b in zip(prior, current)) / 576
        pairs.append((rms, motion))
    baselines = [max(floor, statistics.median(p[k] for p in pairs))
                 for k, floor in enumerate((100, 2))]
    return [(min(5, a / baselines[0]), min(5, m / baselines[1])) for a, m in pairs]


def score(signals, start, end):
    bins = signals[int(start // 2):math.ceil(end / 2)]
    return round(statistics.mean(.58 * a + .42 * m for a, m in bins), 3) if bins else 0


def plan(signals, total, options):
    if options.manual:
        if any(end > total + .02 for _, end in options.manual):
            raise ValueError("Um trecho manual vai além da duração da fonte.")
        return [list(options.manual)]
    length = min(total, options.duration)
    if length == total:
        return [[(0, total)]]
    windows = [(s, s + length) for s in sorted(set([*range(0, int(total - length) + 1, 8), total - length]))]
    if not options.montage:
        ranked = sorted(windows, key=lambda w: score(signals, *w), reverse=True)
        selected = []
        for start, end in ranked:
            if all(end <= a or start >= b for [(a, b)] in selected):
                selected.append([(start, end)])
                if len(selected) == options.count:
                    break
        return selected
    beat = length / 3
    span = min(total, length * 2.5)
    chapters = [(s, min(total, s + span)) for s in range(0, math.ceil(total), max(1, math.ceil(span)))]
    ranked = []
    for low, high in chapters:
        if high - low < length:
            continue
        intervals = []
        for index in range(3):
            a = low + (high - low) * index / 3
            b = low + (high - low) * (index + 1) / 3
            starts = [a + i * 2 for i in range(int(max(0, b - a - beat) // 2) + 1)]
            starts.append(max(a, b - beat))
            start = max(starts, key=lambda s: score(signals, s, s + beat))
            end = start + beat
            if intervals and start - intervals[-1][1] < .05:
                intervals[-1] = (intervals[-1][0], end)
            else:
                intervals.append((start, end))
        ranked.append((sum(score(signals, a, b) * (b - a) for a, b in intervals), intervals))
    return [parts for _, parts in sorted(ranked, reverse=True)[:options.count]]


def crop(region):
    if not region:
        return ""
    x, y, w, h = map(float, region.split(","))
    if (not all(map(math.isfinite, (x, y, w, h))) or min(x, y, w, h) < 0
            or w < .03 or h < .03 or x + w > 1.00001 or y + h > 1.00001):
        raise ValueError("Recorte inválido. Use x,y,largura,altura de 0 a 1.")
    return f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},"


def layout_graph(style, options):
    def fit(region, width, height):
        return (crop(region) + f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2,setsar=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101522")
    face_fill = (crop(options.face) + f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:"
                 f"force_divisible_by=2,crop={WIDTH}:{HEIGHT},setsar=1")
    if style == "split":
        return (f"[0:v]split=2[f][g];[f]{fit(options.face, WIDTH, 440)}[top];"
                f"[g]{fit(options.game, WIDTH, 840)}[bottom];[top][bottom]vstack[base]")
    if style == "reaction":
        x = "W-w-28" if options.corner == "direito" else "28"
        return (f"[0:v]split=2[f][g];[f]{face_fill}[main];"
                f"[g]{fit(options.game, 272, 156)},drawbox=color=white@0.8:t=2[pip];"
                f"[main][pip]overlay={x}:92[base]")
    return f"[0:v]{face_fill if style == 'face' else fit(options.game, WIDTH, HEIGHT)}[base]"


def layouts(signals, start, end, options):
    if not options.face:
        return [(start, end, "game")]
    if options.style != "dynamic":
        return [(start, end, options.style)]
    segments = []
    point = start
    while point < end - .01:
        stop = end if end - point < 12 else point + 8
        bins = signals[int(point // 2):math.ceil(stop / 2)]
        audio, motion = (map(statistics.mean, zip(*bins)) if bins else (0, 0))
        style = "face" if audio >= 1.25 and audio > motion * 1.45 else (
            "game" if motion >= 1.25 and motion > audio * 1.25 else "split")
        if segments and segments[-1][2] == style:
            segments[-1] = (segments[-1][0], stop, style)
        else:
            segments.append((point, stop, style))
        point = stop
    return segments


def stamp(seconds):
    ticks = max(0, round(seconds * 100))
    return f"{ticks // 360000}:{ticks // 6000 % 60:02}:{ticks // 100 % 60:02}.{ticks % 100:02}"


def transcribe(source, start, end, folder):
    audio = folder / "speech.wav"
    command(FF + ["-y", "-ss", str(start), "-i", str(source), "-t", str(end - start),
                  "-vn", "-ac", "1", "-ar", "16000", str(audio)])
    try:
        with MODEL_LOCK:
            from faster_whisper import WhisperModel
            if "base" not in MODELS:
                MODELS["base"] = WhisperModel("base", device="cpu", compute_type="int8",
                                              download_root=str(Path(__file__).parent / "models"))
            segments, _ = MODELS["base"].transcribe(str(audio), word_timestamps=True, vad_filter=True)
            return [(start + w.start, start + w.end, w.word.strip())
                    for s in segments for w in (s.words or []) if w.word.strip()]
    finally:
        audio.unlink(missing_ok=True)


def subtitles(path, words, start, end, style):
    y = 495 if style == "split" else 1035
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,48,&H0000DEFF,&H00FFFFFF,&H00101218,&H60000000,-1,0,0,0,100,100,0,0,1,4,1,5,50,50,40,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    words = [(max(a, start), min(b, end), word) for a, b, word in words if a < end and b > start]
    lines = []
    for i in range(0, len(words), 3):
        group = words[i:i + 3]
        for j, (a, b, _) in enumerate(group):
            limit = group[j + 1][0] if j + 1 < len(group) else min(end, b + .13)
            if limit <= a:
                continue
            phrase = " ".join((r"{\1c&H00DEFF&}" if k == j else r"{\1c&HFFFFFF&}")
                              + re.sub(r"[{}\\\r\n]", "", word)
                              for k, (_, _, word) in enumerate(group))
            lines.append(f"Dialogue: 0,{stamp(a-start)},{stamp(limit-start)},Caption,,0,0,0,"
                         + r"{\pos(360," + str(y) + ")}" + phrase)
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def process(source, folder, options, log):
    folder.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    total, audio = probe(source)
    log(f"Analisando {source.name} ({total / 60:.1f} min)")
    signals = inspect(source, total, audio)
    selected = plan(signals, total, options)
    report = {"schema": 1, "source": str(source), "duration": total, "unit": "seconds",
              "method": "manual" if options.manual else "relative_audio_and_motion", "clips": []}
    for parts in selected:
        report["clips"].append({"parts": [{"start": a, "end": b, "score": score(signals, a, b)}
                                          for a, b in parts],
                                "layouts": [dict(start=a, end=b, style=s) for low, high in parts
                                            for a, b, s in layouts(signals, low, high, options)]})
    report_path = folder / "cortes.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"{len(selected)} corte(s) selecionado(s) em {folder.name}")
    if not options.render:
        return
    for index, parts in enumerate(selected, 1):
        scratch = folder / f"trechos_{index:02}"
        scratch.mkdir()
        pieces = []
        for low, high in parts:
            words = transcribe(source, low, high, scratch) if options.captions and audio else []
            for start, end, style in layouts(signals, low, high, options):
                name = f"p{len(pieces):03}.mp4"
                graph = layout_graph(style, options)
                if words:
                    subtitles(scratch / "legend.ass", words, start, end, style)
                    graph += ";[base]ass=legend.ass[out]"
                else:
                    graph += ";[base]null[out]"
                command(FF + ["-y", "-threads", "2", "-ss", str(start), "-i", str(source),
                              "-filter_complex_threads", "1", "-filter_complex", graph,
                              "-map", "[out]", "-map", "0:a:0?", "-t", str(end - start),
                              "-r", "30"] + encoder() + ENC + [name], cwd=scratch)
                pieces.append(name)
        listing = scratch / "join.txt"
        listing.write_text("".join(f"file '{name}'\n" for name in pieces), encoding="ascii")
        destination = folder / f"clip_{index:02}.mp4"
        partial = folder / f"clip_{index:02}.partial.mp4"
        command(FF + ["-y", "-f", "concat", "-safe", "1", "-i", listing.name,
                      "-c", "copy", "-movflags", "+faststart", str(partial)], cwd=scratch)
        partial.replace(destination)
        report["clips"][index - 1]["output"] = destination.name
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        for name in [*pieces, "join.txt", "legend.ass"]:
            (scratch / name).unlink(missing_ok=True)
        scratch.rmdir()
        log(f"Pronto: {destination}")


def twitch_source(value):
    parsed = urlparse(value if "://" in value else f"https://www.twitch.tv/{value}")
    if parsed.scheme not in ("https", "http") or parsed.netloc.lower() not in ("twitch.tv", "www.twitch.tv"):
        raise ValueError("Informe um canal ou VOD público da Twitch.")
    path = parsed.path.strip("/")
    if not re.fullmatch(r"(?:videos/[0-9]+|[a-zA-Z0-9_]{1,25})", path):
        raise ValueError("Canal ou ID de VOD inválido.")
    return "https://www.twitch.tv/" + path, path.startswith("videos/")


def fetch_vod(python, url, folder):
    path = folder / "vod.ts"
    command([python, "-m", "streamlink", "--loglevel", "error", "--output", str(path),
             url, "720p,480p,best"], timeout=21600)
    return path


def capture(python, url, folder, minutes, schedule, stop, log):
    """Keep one capture connection per channel; queue only closed segments."""
    seen = set()
    index = folder / "captura.csv"
    deadline = time.monotonic() + minutes * 60 + 40

    def queue_finished():
        if not index.exists():
            return
        rows = list(csv.reader(index.read_text(encoding="utf-8").splitlines()))
        for row in rows:
            if len(row) != 3 or row[0] in seen or not re.fullmatch(r"live_\d+\.ts", row[0]):
                continue
            path = folder / row[0]
            if path.exists():
                seen.add(row[0])
                if path.stat().st_size and float(row[2]) - float(row[1]) >= 8:
                    schedule(path, folder / path.stem)

    with (folder / "captura.log").open("wb") as errors:
        sl = sp.Popen([python, "-m", "streamlink", "--stdout", "--twitch-low-latency",
                       "--loglevel", "warning", url, "480p,360p,best"], stdout=sp.PIPE, stderr=errors)
        ff = None
        try:
            ff = sp.Popen(FF + ["-i", "pipe:0", "-map", "0:v:0", "-map", "0:a:0?",
                                "-t", str(minutes * 60), "-c", "copy", "-f", "segment",
                                "-segment_time", "180", "-reset_timestamps", "1",
                                "-segment_list", index.name, "-segment_list_type", "csv",
                                "live_%04d.ts"], stdin=sl.stdout, cwd=folder, stderr=errors)
            sl.stdout.close()
            log(f"Capturando {url}")
            while ff.poll() is None and not stop.wait(2) and time.monotonic() < deadline:
                queue_finished()
        finally:
            sl.stdout.close()
            if sl.poll() is None:
                sl.terminate()
            sl.wait()
            if ff is not None:
                try:
                    ff.wait(timeout=12)
                except sp.TimeoutExpired:
                    ff.kill()
                    ff.wait()
    queue_finished()
    if not seen:
        log(f"Nenhum bloco capturado de {url}. Consulte {folder / 'captura.log'}")
