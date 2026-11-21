"""Local ingestion, highlight selection and vertical rendering."""
import array
import csv
import json
import math
import os
import re
import shutil
import statistics
import subprocess as sp
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse
from editorial import (Cleanup, clean_ranges, quiet_live_edits, refine_montage,
                       silence_edits, speech_gap_edits, transcript_edits)
from facecam import estimate, gameplay_region
from broll_library import Asset, STILLS
from finishing import accent_shots, caption_groups, pick_broll
from effects_bank import edge_transition, render_cues
from compression import compress
import runtime_profile as runtime

WIDTH, HEIGHT = 720, 1280
CAPTURE_HEIGHTS = (480, 720, 1080, 1440, 2160)
REPLAY_HEIGHTS = (1080, 1440, 2160)
LIVE_VARIANTS = "2160p60,2160p,1440p60,1440p,1080p60,1080p,936p60,936p,900p60,900p,864p60,864p,720p60,720p,540p,480p60,480p,360p,240p,160p".split(",")


def live_variant_order(height):
    return ",".join(name for name in LIVE_VARIANTS if int(name.split("p")[0]) <= height)
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
    cleanup: Cleanup = Cleanup()
    auto_face: bool = False
    look: str = "classic"
    hook: bool = False
    polish: bool = False
    broll_dir: str = ""
    close_focus: float = 0.5
    voice_polish: bool = False
    jcut_ms: int = 0
    music: str = ""
    music_db: int = -25
    transition: str = "zoom"
    sfx: str = "auto"
    sfx_peak: int = -8
    compression: str = "original"
    save_review: bool = True
    broll_assets: tuple = ()
    contextual_broll: bool = True
    auto_music: bool | None = None
    keep_manual_edges: bool = False
    trim_inactive: bool = False
    channel_handle: str = ""
    hook_text: str = ""
    effects_model: str = ""
    smart_reframe: bool = False
    speech_language: str = "auto"
    target_shot_seconds: float = 3.0
    full_hd: bool = False
    precompress: bool = True
    visual_library: tuple[Asset, ...] = ()
    visual_background: str = "original"
    background_asset: Asset | None = None
    review_visuals: bool = False
    preview_resolution: bool = False
    visual_disabled: bool = False
    visual_plan: tuple[int, float, Asset] | None = None

    @property
    def frame_size(self):
        if self.preview_resolution:
            return 360, 640
        return (1080, 1920) if self.full_hd else (WIDTH, HEIGHT)

    def __post_init__(self):
        handle = self.channel_handle.strip()
        if handle:
            handle = handle.removeprefix("@")
            if not re.fullmatch(r"[\w.-]{1,30}", handle):
                raise ValueError("Use até 30 caracteres no @ do canal. São aceitos letras, números, ponto, hífen e sublinhado.")
            handle = "@" + handle
        object.__setattr__(self, "channel_handle", handle)
        if self.speech_language not in ("auto", "pt", "en", "es"):
            raise ValueError("Idioma de fala inválido.")
        if not 1.5 <= self.target_shot_seconds <= 5.2:
            raise ValueError("Ritmo de câmera fora do intervalo suportado.")


def command(args, **kwargs):
    result = sp.run(runtime.multimedia_args(args), capture_output=True, **runtime.child_options(), **kwargs)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(message[:1000] or str(args[0]))
    return result.stdout


@lru_cache(maxsize=1)
def encoder(*, software_only=False, quality=22):
    hardware = None if software_only else runtime.hardware_encoder("h264", quality)
    if hardware:
        return hardware
    available = command(FF + ["-encoders"]).decode("utf-8", "replace")
    if re.search(r"\blibx264\b", available):
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(quality)]
    if re.search(r"\blibopenh264\b", available):
        return ["-c:v", "libopenh264", "-b:v", "4M"]
    raise RuntimeError("O FFmpeg precisa do encoder libx264 ou libopenh264.")


def probe(source, *, timeout=None):
    data = json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                               "-of", "json", str(source)], timeout=timeout))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("Fonte sem vídeo.")
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duração da fonte indisponível.")
    return duration, any(s["codec_type"] == "audio" for s in data["streams"])


def media_for_seeking(source, remuxed):
    if source.suffix.lower() not in {".ts", ".mts", ".m2ts"}:
        return source
    command(FF + ["-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
                  "-c", "copy", "-movflags", "+faststart", str(remuxed)])
    return remuxed


def detect_facecam(source, duration):
    width, height = 640, 360
    points = [duration * i / 13 for i in range(1, 13)]
    frames = []
    for point in points:
        frame = command(FF + ["-threads", "2", "-ss", str(point), "-i", str(source),
                              "-an", "-frames:v", "1", "-vf", f"scale={width}:{height},format=gray",
                              "-c:v", "rawvideo", "-threads", "1", "-f", "rawvideo", "pipe:1"])
        if len(frame) == width * height:
            frames.append(frame)
    return estimate(frames, width, height)


def inspect(source, duration, audio, face="", *, normalized=True, start=0., video=True):
    """Two-second samples. No rendering or speech model needed for this pass."""
    window = (["-ss", str(start), "-i", str(source), "-t", str(duration)]
              if start else ["-i", str(source), "-t", str(duration)])
    pcm = array.array("h")
    if audio:
        pcm.frombytes(command(FF + ["-threads", "2", *window, "-vn", "-ac", "1",
                                    "-ar", "800", "-f", "s16le", "pipe:1"]))
    width, height = 64, 36
    size = width * height
    frames = command(FF + ["-threads", "2", "-filter_threads", "1", *window,
                          "-an", "-vf", f"fps=1/2,scale={width}:{height},format=gray",
                          "-c:v", "rawvideo", "-threads", "1", "-f", "rawvideo", "pipe:1"]) if video else b""
    face_pixels = set()
    if face:
        x, y, w, h = map(float, face.split(","))
        face_pixels = {row * width + col for row in range(int(y * height), min(height, math.ceil((y + h) * height)))
                       for col in range(int(x * width), min(width, math.ceil((x + w) * width)))}
    pairs = []
    for i in range(math.ceil(duration / 2)):
        samples = pcm[i * 1600:(i + 1) * 1600]
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0
        current = frames[i * size:(i + 1) * size]
        prior = frames[(i - 1) * size:i * size] if i else b""
        changes = [abs(a - b) for a, b in zip(prior, current)]
        cam_motion = sum(changes[p] for p in face_pixels) if len(changes) == size else 0
        motion = (sum(changes) - cam_motion) / max(1, size - len(face_pixels))
        pairs.append((rms, motion, cam_motion / max(1, len(face_pixels))))
    if not normalized:
        return pairs
    baselines = [max(floor, statistics.median(p[k] for p in pairs))
                 for k, floor in enumerate((100, 2, 2))]
    return [tuple(min(5, value / baseline) for value, baseline in zip(pair, baselines)) for pair in pairs]


def score(signals, start, end, offset=0):
    bins = signals[int((start-offset) // 2):math.ceil((end-offset) / 2)]
    return round(statistics.mean(.58 * pair[0] + .42 * pair[1] for pair in bins), 3) if bins else 0


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


def layout_graph(style, options, focus_x=None):
    portrait_fill = options.smart_reframe and options.transition == "v9"
    canvas_width, canvas_height = options.frame_size

    def scale_units(pixels):
        return round(pixels * canvas_width / WIDTH / 2) * 2

    def fit(region, width, height):
        return (crop(region) + f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2,setsar=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101522")
    def game_canvas(source, target):
        if focus_x is not None or portrait_fill:
            anchor = .5 if focus_x is None else focus_x
            return (f"{source}{crop(options.game)}scale={canvas_width}:{canvas_height}:force_original_aspect_ratio=increase:"
                    f"force_divisible_by=2,crop={canvas_width}:{canvas_height}:(iw-ow)*{anchor}:(ih-oh)/2,setsar=1{target}")
        return (f"{source}{crop(options.game)}split=2[back][play];"
                f"[back]scale=180:320:force_original_aspect_ratio=increase:force_divisible_by=2,"
                f"crop=180:320,gblur=sigma=12,drawbox=c=black@0.24:t=fill,"
                f"scale={canvas_width}:{canvas_height},setsar=1[blur];"
                f"[play]scale={canvas_width}:{canvas_height}:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2,setsar=1[active];"
                f"[blur][active]overlay=(W-w)/2:(H-h)/2{target}")
    def fill(region, height):
        return (crop(region) + f"scale={canvas_width}:{height}:force_original_aspect_ratio=increase:"
                f"force_divisible_by=2,crop={canvas_width}:{height},setsar=1")
    focus = options.close_focus
    v9_close = options.polish and options.transition == "v9"
    visible_width = (.85 if v9_close else 1) - (.24 if v9_close else .30) * abs(2 * focus - 1)
    face_focus = (f"crop=iw*{visible_width}:ih:(iw-ow)*{focus}:0,"
                  if v9_close or focus != .5 else "")

    def face_canvas(source, target):
        if portrait_fill:
            return (f"{source}{crop(options.face)}scale={canvas_width}:{canvas_height}:force_original_aspect_ratio=increase:"
                    f"force_divisible_by=2,crop={canvas_width}:{canvas_height}:(iw-ow)*{focus}:(ih-oh)/2,setsar=1{target}")
        return (f"{source}{crop(options.face)}split=2[facebg][facefg];"
                f"[facebg]scale=180:320:force_original_aspect_ratio=increase:force_divisible_by=2,"
                f"crop=180:320:(iw-ow)*{focus},gblur=sigma=14,drawbox=c=black@0.30:t=fill,"
                f"scale={canvas_width}:{canvas_height},setsar=1[soft];"
                f"[facefg]{face_focus}scale={canvas_width}:{scale_units(850)}:flags=lanczos:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2,setsar=1[talent];"
                f"[soft][talent]overlay=(W-w)/2:{round(175 * canvas_width / WIDTH)}{target}")
    if style == "gamecam":
        margin = scale_units(22)
        x = f"W-w-{margin}" if options.corner == "direito" else str(margin)
        side = scale_units(196)
        circle = ("format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                  "a='if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2-2)*(W/2-2)),255,0)'")
        camera = (crop(options.face) + f"scale={side}:{side}:force_original_aspect_ratio=increase:"
                  f"force_divisible_by=2,crop={side}:{side}:(iw-ow)*{focus}:(ih-oh)/2,setsar=1," + circle)
        return (f"[0:v]split=2[f][g];{game_canvas('[g]', '[main]')};"
                f"[f]{camera}[cam];[main][cam]overlay={x}:{scale_units(190)}[base]")
    if style == "split":
        if options.look == "shorts":
            return (f"[0:v]split=2[f][g];[f]{fill(options.face, scale_units(500))}[top];"
                    f"[g]{fill(options.game, scale_units(780))}[bottom];[top][bottom]vstack[base]")
        return (f"[0:v]split=2[f][g];[f]{fit(options.face, canvas_width, scale_units(440))}[top];"
                f"[g]{fit(options.game, canvas_width, scale_units(840))}[bottom];[top][bottom]vstack[base]")
    if style == "reaction":
        margin = scale_units(28)
        x = f"W-w-{margin}" if options.corner == "direito" else str(margin)
        return (f"[0:v]split=2[f][g];{face_canvas('[f]', '[main]')};"
                f"[g]{fit(options.game, scale_units(272), scale_units(156))},drawbox=color=white@0.8:t=2[pip];"
                f"[main][pip]overlay={x}:{scale_units(92)}[base]")
    if style == "face":
        return face_canvas("[0:v]", "[base]")
    return game_canvas("[0:v]", "[base]")


def layouts(signals, start, end, options, words=(), signal_offset=0):
    if not options.face:
        return [(start, end, "game")]
    if options.style != "dynamic":
        return [(start, end, options.style)]
    segments = []
    point = start
    target = options.target_shot_seconds
    earliest = max(1.4, target - 1.1)
    latest = target + .7
    while point < end - .01:
        v9 = options.transition == "v9"
        if v9 and end - point > latest:
            desired = point + target
            # Prefer a complete phrase or a natural gap over cutting the framing mid-word.
            possible = [b for i, (_, b, text) in enumerate(words) if point + earliest <= b <= point + latest
                        and (text.endswith((".", "!", "?")) or
                             (i + 1 < len(words) and words[i + 1][0] - b >= .22))]
            stop = min(possible, key=lambda moment: abs(moment - desired)) if possible else desired
            if end - stop < 1.4:
                stop = end
        else:
            stop = end if end - point < 8 else point + 4
        bins = signals[int((point-signal_offset) // 2):math.ceil((stop-signal_offset) / 2)]
        activity = [statistics.mean(values) for values in zip(*bins)] if bins else []
        audio, motion, cam = (activity + [0, 0, 0])[:3]
        spoken = [text for a, _, text in words if point <= a < stop]
        reaction = any("!" in text or text.casefold().strip("!?.,") in
                       {"caramba", "nossa", "mano", "wow", "eita"} for text in spoken)
        action_only = v9 and not spoken and motion >= 1.22 and motion >= 1.45 * cam
        if action_only:
            style = "game"
        elif (cam >= 1.45 and audio >= 1.2 and motion < cam * 1.4) or (
                reaction and audio >= (1.22 if v9 else 1.4) and cam >= 1.05):
            style = "face"
        elif motion >= 1.35 and motion > max(cam, audio) * 1.25:
            style = "game"
        elif motion >= (1.18 if options.look == "shorts" else 1.0) and cam < 1.15:
            style = "gamecam"
        else:
            style = "split"
        if segments and segments[-1][2] == style:
            segments[-1] = (segments[-1][0], stop, style)
        else:
            segments.append((point, stop, style))
        point = stop
    return segments


def stamp(seconds):
    ticks = max(0, round(seconds * 100))
    return f"{ticks // 360000}:{ticks // 6000 % 60:02}:{ticks // 100 % 60:02}.{ticks % 100:02}"


def speech_model_path(model):
    from faster_whisper.utils import download_model
    from huggingface_hub.errors import LocalEntryNotFoundError

    root = Path(__file__).resolve().parent
    local = os.getenv("LOCALAPPDATA")
    shared = Path(local) / "Codex Video" / "Models" if local else Path.home() / ".cache/codex-video/models"
    candidates = [shared, root / "models"]
    programs = Path(local) / "Programs" if local else root.parent
    if programs.is_dir():
        candidates.extend(folder / "models" for folder in programs.iterdir()
                          if re.fullmatch(r"(?:Cortex Clip Studio |Codex Video )\d+\.\d+\.\d+|Clip-Studio-v\d+\.\d+\.\d+-\d+", folder.name)
                          and (folder / "VERSION").is_file() and folder.resolve() == folder)
    for cache in dict.fromkeys(candidates):
        if not cache.is_dir():
            continue
        try:
            path = Path(download_model(model, local_files_only=True, cache_dir=str(cache)))
        except (LocalEntryNotFoundError, OSError):
            continue
        if all((path / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
            return str(path)
    return download_model(model, cache_dir=str(shared))


def transcribe(source, start, end, model=None, *, language="auto"):
    import numpy as np
    from faster_whisper import WhisperModel

    model = model or ("tiny" if runtime.active.low_priority else "base")
    pcm = command(FF + ["-threads", "1", "-ss", str(start), "-i", str(source), "-t", str(end - start),
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"])
    if not pcm:
        return []
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    with MODEL_LOCK:
        threads = runtime.active.whisper_threads
        entry = MODELS.get(model)
        device = "cpu"
        if runtime.acceleration == "auto" and runtime.cuda_transcription:
            from ctranslate2 import get_cuda_device_count
            try:
                device = "cuda" if get_cuda_device_count() else "cpu"
            except RuntimeError:
                pass
        if not entry or entry[0] != (threads, device):
            MODELS.clear()

        def load(target):
            return WhisperModel(speech_model_path(model), device=target,
                                compute_type="int8_float16" if target == "cuda" else "int8",
                                cpu_threads=threads, num_workers=1)

        def words(whisper):
            segments, _ = whisper.transcribe(samples, word_timestamps=True, vad_filter=True,
                                             beam_size=1 if model == "tiny" else 5,
                                             language=None if language == "auto" else language)
            return [(float(start + w.start), float(start + w.end), w.word.strip())
                    for s in segments for w in (s.words or []) if w.word.strip()]

        try:
            if model not in MODELS:
                MODELS[model] = ((threads, device), load(device))
            return words(MODELS[model][1])
        except RuntimeError:
            if device != "cuda" or not runtime.cuda_transcription:
                raise
            runtime.cuda_transcription = False
            MODELS.clear()
            MODELS[model] = ((threads, "cpu"), load("cpu"))
            return words(MODELS[model][1])


def audio_silences(source, low, high, cleanup):
    result = sp.run(["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostdin",
                     "-ss", str(low), "-i", str(source), "-t", str(high - low),
                     "-vn", "-map", "0:a:0", "-af",
                     f"silencedetect=noise={cleanup.noise}dB:d={cleanup.pause}",
                     "-f", "null", "-"], capture_output=True, check=False)
    log = result.stderr.decode("utf-8", "replace")
    if result.returncode:
        raise RuntimeError(f"Falha ao medir silêncio: {log[-500:]}")
    return list(silence_edits(log, low, high, cleanup.padding))


def ass_text(value):
    return re.sub(r"[{}\\\r\n]", "", value)


def opening_phrase(words, start):
    opening = [(a, b, word) for a, b, word in words if start <= a <= start + 7]
    chosen = []
    for _, _, word in opening:
        cleaned = ass_text(word).strip()
        if not cleaned:
            continue
        if len(" ".join([*chosen, cleaned])) > 64:
            break
        chosen.append(cleaned)
        if len(chosen) >= 4 and (cleaned.endswith((".", "!", "?")) or len(chosen) == 8):
            break
    connectors = {"e", "ou", "mas", "que", "de", "da", "do", "dos", "das", "para", "com",
                  "and", "or", "but", "the", "a", "an", "of", "to", "with"}
    while chosen and chosen[-1].casefold().strip(".,:;!?") in connectors:
        chosen.pop()
    return " ".join(chosen).strip(" .,:;") if len(chosen) >= 4 else ""


def subtitles(path, words, start, end, style, look="classic", hook="", opening=None, *, channel_handle=""):
    y = (562 if look == "shorts" else 495) if style == "split" else 1035
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,48,&H0000DEFF,&H00FFFFFF,&H00101218,&H60000000,-1,0,0,0,100,100,0,0,1,4,1,5,50,50,40,1
Style: Hook,Arial,44,&H00FFFFFF,&H00FFFFFF,&H00131824,&H00131824,-1,0,0,0,100,100,0,0,3,11,0,5,106,106,30,1
Style: Channel,Segoe UI,36,&H20FFFFFF,&H20FFFFFF,&H38101620,&H62000000,-1,0,0,0,100,100,0,0,1,2.5,1,8,28,28,26,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if channel_handle:
        lines.append(f"Dialogue: 2,{stamp(0)},{stamp(end-start+.04)},Channel,,0,0,0,,"
                     + r"{\pos(360,118)}" + ass_text(channel_handle))
    if hook and opening is not None and start < opening + 2.7 and end > opening:
        at, until = max(start, opening), min(end, opening + 2.7)
        hook_y = 415 if style == "split" else 280
        lines.append(f"Dialogue: 1,{stamp(at-start)},{stamp(until-start)},Hook,,0,0,0,,"
                     + r"{\pos(360," + str(hook_y) + ")}" + ass_text(hook))
    groups = list(caption_groups(words))
    for index, group in enumerate(groups):
        if group[0][0] >= end or group[-1][1] + .13 <= start:
            continue
        for j, (a, b, _) in enumerate(group):
            if j + 1 < len(group):
                next_word = group[j + 1][0]
            elif index + 1 < len(groups):
                next_word = min(b + .13, groups[index + 1][0][0])
            else:
                next_word = b + .13
            limit, at = min(end, next_word, b + .19), max(start, a)
            if stamp(limit-start) == stamp(at-start) or limit <= at:
                continue
            phrase = " ".join((r"{\1c&H00DEFF&}" if k == j else r"{\1c&HFFFFFF&}")
                              + (ass_text(word).upper() if look == "shorts" else ass_text(word))
                              for k, (_, _, word) in enumerate(group))
            lines.append(f"Dialogue: 0,{stamp(at-start)},{stamp(limit-start)},Caption,,0,0,0,,"
                         + r"{\pos(360," + str(y) + ")}" + phrase)
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def render_clip(source, destination, shots, words, options, hook="", timing_words=None):
    compact = runtime.active.low_priority and options.compression == "compacto"
    selected = encoder(quality=24 if compact else 22)
    hardware = selected[1].endswith(("_nvenc", "_amf", "_qsv"))
    attempts = (selected, None) if hardware else (selected,)
    for attempt in attempts:
        video_encoder = attempt or encoder(software_only=True, quality=24 if compact else 22)
        with TemporaryDirectory(prefix=".render-", dir=destination.parent) as directory:
            try:
                report = _render_clip(source, destination, shots, words, options, Path(directory), hook,
                                      timing_words, video_encoder)
                report["gpu_fallback"] = attempt is None
                return report
            except RuntimeError:
                if not hardware or attempt is None:
                    raise


def _render_clip(source, destination, shots, words, options, scratch, hook, timing_words, video_encoder):
    width, height = options.frame_size
    from audio_finish import loudness_filter, make_mix, program

    from v9_finish import background_graph, contextual_card, music_bed

    source = media_for_seeking(source, scratch / "source.mp4")
    total, audio = probe(source)
    pieces = []
    compact_once = (runtime.active.low_priority and options.compression == "compacto"
                    and video_encoder[1] != "libopenh264")
    v9 = options.polish and options.transition == "v9"
    accents = accent_shots(shots) if options.polish else {}
    spoken = timing_words if timing_words is not None else words
    pending_assets = {asset.path: asset for asset in options.visual_library}
    inserts = {}
    while not options.visual_disabled and options.visual_plan is None:
        picked = tuple((asset.path, asset.cues) for asset in pending_assets.values())
        inserts = pick_broll(options.broll_dir, shots, spoken, full_screen=v9, selected=picked + options.broll_assets,
                             reaction=bool(pending_assets))
        selected = next(iter(inserts.values()), (None, None))[0]
        asset = pending_assets.get(selected)
        if asset is None or asset.is_current():
            break
        del pending_assets[selected]
    if options.visual_plan is not None:
        shot, at, planned = options.visual_plan
        if not planned.is_current():
            raise ValueError("A mídia escolhida mudou. Selecione outra inserção.")
        pending_assets[planned.path] = planned
        inserts = {shot: (planned.path, at)}
    generated = contextual_card(scratch, shots, spoken) if v9 and options.contextual_broll and not inserts else {}
    inserts = inserts or generated
    background = options.background_asset
    backdrop_mode = options.visual_background
    if backdrop_mode in {"director", "file", "catalog"} and not (background and background.is_current()):
        backdrop_mode = "original"
    background_shots = []
    visual_credits = {}

    def visual_input(asset_path):
        return (["-loop", "1"] if asset_path.suffix.lower() in STILLS else ["-stream_loop", "-1"]) + ["-i", str(asset_path)]
    dissolve = next((i for i, (start, end, style) in enumerate(shots) if i and style == "face"
                     and end - start >= .9 and shots[i - 1][2] in {"game", "gamecam", "split"}
                     and shots[i - 1][1] - shots[i - 1][0] >= 1.35
                     and shots[i - 1][1] + .24 < total), None) if v9 else None
    blends, v9_cues = [], []
    music = str(Path(options.music).resolve()) if options.music else ""
    auto_music = v9 if options.auto_music is None else options.auto_music
    if auto_music and not music and audio:
        music = str(music_bed(scratch / "pulso-v9.wav"))
    elapsed = 0.0
    frame_counts = []
    punches = []
    for index, (start, end, style) in enumerate(shots):
        frame_start = round(elapsed * 30)
        elapsed += end - start
        frames = max(1, round(elapsed * 30) - frame_start)
        frame_counts.append(frames)
        name = f"p{len(pieces):03}.mp4"
        focus_x = None
        if options.smart_reframe and style == "game" and not options.face and not options.game:
            from creative_studio import shot_focus
            focus_x = shot_focus(source, start, end)
        graph = layout_graph(style, options, focus_x)
        layer = "[base]"
        inputs = []
        opening_punch = index == 0 and (style == "face" or (style == "split" and hook))
        highlight_punch = (index in accents or index == dissolve) and style == "face"
        if v9 and frames >= 27 and (opening_punch or highlight_punch):
            from v9_finish import camera_move

            amount = .065 if highlight_punch else .045
            # Anchor the reframe in the portrait, including the split's upper panel.
            anchor = (.50, .38 if style == "split" else .43)
            graph += camera_move(layer, "[punch]", frames, amount, anchor, size=(width, height))
            punches.append({"shot": index + 1, "zoom": 1 + amount, "anchor": anchor,
                            "attack_frames": 8, "return_frames": 10 if frames >= 42 else 0})
            layer = "[punch]"
        elif options.polish and options.transition == "zoom" and end - start >= .9 and (opening_punch or highlight_punch):
            amount = .09 if highlight_punch else .04
            punches.append({"shot": index + 1, "zoom": 1+amount, "return_frames": 0})
            graph += (f";{layer}fps=30,zoompan=z='1+{amount}*(1-exp(-on/4))':"
                      f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps=30[punch]")
            layer = "[punch]"
        if options.polish and options.transition == "linha" and index in accents:
            graph += edge_transition(layer, "[transition]")
            layer = "[transition]"
        next_input = 1
        if v9 and backdrop_mode != "original" and style in {"face", "reaction"}:
            backdrop_input = None
            if backdrop_mode in {"director", "file", "catalog"}:
                backdrop_input = next_input
                inputs += visual_input(background.path)
                next_input += 1
                if background.digest:
                    visual_credits[background.key] = background.credit()
            graph += background_graph(layer, width, height, backdrop_input)
            layer = "[editorial_bg]"
            background_shots.append(index + 1)
        insert_full = False
        if index in inserts:
            path, at = inserts[index]
            registered = pending_assets.get(path)
            insert_full = v9 and path.stem.casefold().startswith("tela-") and not (
                registered and registered.role in {"meme", "meme-br"})
            inputs += visual_input(path)
            detail_source = f"[{next_input}:v]"
            next_input += 1
            if registered and registered.digest:
                visual_credits[registered.key] = registered.credit()
            if insert_full:
                graph += (f";{detail_source}fps=30,trim=duration=1.15,setpts=PTS-STARTPTS,"
                          f"scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
                          f"crop={width}:{height},setsar=1,setpts=PTS+{at:.3f}/TB[detail];"
                          f"{layer}[detail]overlay=0:0:eof_action=pass:"
                          f"enable='gte(t,{at:.3f})*lt(t,{at+1.15:.3f})'[inserted]")
            else:
                slide = f":x='W-w-48+14*max(0,1-(t-{at:.3f})/0.16)^2':y=680" if v9 else ":x=W-w-48:y=680"
                detail_w, detail_h = 290, 164
                if registered:
                    detail_w, detail_h = round(width / 6) * 2, round(width * .1) * 2
                    margin = round(width * .06)
                    close = style in {"face", "reaction"}
                    x = f"W-w-{margin}+" if close else f"{margin}-"
                    y = round(height * (.67 if close else .60))
                    slide = f":x='{x}15*max(0,1-(t-{at:.3f})/0.16)^2':y={y}"
                graph += (f";{detail_source}fps=30,trim=duration=1.15,setpts=PTS-STARTPTS,"
                          f"scale={detail_w}:{detail_h}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                          f"pad={detail_w}:{detail_h}:(ow-iw)/2:(oh-ih)/2,drawbox=c=white@0.7:t=2,format=yuva420p,"
                          "fade=t=in:d=0.10:alpha=1,fade=t=out:st=1.02:d=0.12:alpha=1,"
                          f"setpts=PTS+{at:.3f}/TB[detail];"
                          f"{layer}[detail]overlay=eof_action=pass{slide}:"
                          f"enable='between(t,{at:.3f},{at+1.15:.3f})'[inserted]")
            layer = "[inserted]"
        if v9 and style == "face":
            graph += f";{layer}hue=s=1.035,unsharp=5:5:0.25[graded]"
            layer = "[graded]"
        elif v9 and style in {"game", "gamecam"}:
            graph += f";{layer}curves=all='0/0.006 0.2/0.218 0.75/0.76 1/1',format=yuv420p[graded]"
            layer = "[graded]"
        if index == dissolve:
            outgoing = scratch / "cauda.mp4"
            _, tail, previous_style = shots[index - 1]
            tail_graph = layout_graph(previous_style, options) + ";[base]fps=30,setsar=1,format=yuv420p[out]"
            command(FF + ["-y", "-threads", "2", "-ss", str(tail), "-i", str(source),
                          "-filter_complex_threads", "1", "-filter_complex", tail_graph,
                          "-map", "[out]", "-an", "-frames:v", "7", *video_encoder, *ENC, str(outgoing)])
            input_index = next_input
            inputs += ["-i", str(outgoing)]
            graph += (f";[{input_index}:v]fps=30,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[tail];"
                      f"{layer}fps=30,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[incoming];"
                      "[tail][incoming]xfade=transition=fade:duration=0.166667:offset=0[blended]")
            layer = "[blended]"
            blends.append({"frame": frame_start, "duration_frames": 5})
        if v9 and options.sfx != "nenhum":
            if index in inserts:
                v9_cues.append((frame_start / 30 + inserts[index][1], "whoosh" if insert_full else
                                "impacto" if registered else "radio", -18 if registered else -15))
            if index == dissolve:
                v9_cues.append(((frame_start - 1) / 30, "impacto", -12))
        if words or hook or options.channel_handle:
            # Keep the channel mark active on the entire shot, including a rounded-up final frame.
            subtitles(scratch / "legend.ass", words, start, end, style, options.look, hook, shots[0][0],
                      channel_handle=options.channel_handle)
            graph += f";{layer}ass=legend.ass[out]"
        else:
            graph += f";{layer}null[out]"
        command(FF + ["-y", "-threads", "2", "-ss", str(start), "-i", str(source),
                      *inputs, "-filter_complex_threads", "1", "-filter_complex", graph,
                      "-map", "[out]", "-an", "-r", "30", "-frames:v", str(frames)]
                + video_encoder + ENC + [name], cwd=scratch)
        pieces.append(name)
    listing = scratch / "join.txt"
    listing.write_text("".join(f"file '{name}'\n" for name in pieces), encoding="ascii")
    partial = scratch / "joined.mp4"
    join = FF + ["-y", "-f", "concat", "-safe", "1", "-i", listing.name]
    cues = [(time, options.sfx if options.sfx != "auto" else
             {"face": "impacto", "gamecam": "radio"}.get(shots[index][2], "whoosh"))
            for index, time in accents.items()] if options.sfx != "nenhum" and not v9 else v9_cues
    jcuts, gains = [], []
    if audio or music or cues:
        duration = sum(frame_counts) / 30
        if audio:
            jcuts, gains = program(lambda args: command(FF + args), source, shots, frame_counts,
                                   scratch / "program.wav", options.jcut_ms, options.voice_polish)
        else:
            command(FF + ["-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                          "-t", str(duration), "program.wav"], cwd=scratch)
        if cues:
            render_cues(scratch / "cues.wav", duration, cues, options.sfx_peak)
        if cues or music or options.voice_polish:
            make_mix(FF, command, scratch, duration, options.voice_polish, music,
                     -21 if v9 and options.auto_music is None and not options.music else options.music_db, bool(cues))
            join += ["-i", "mix.wav", "-map", "1:a:0"]
            if options.voice_polish:
                join += ["-af", loudness_filter(FF, scratch), "-ar", "48000"]
        else:
            join += ["-i", "program.wav", "-map", "1:a:0"]
        join += ["-map", "0:v:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        join += ["-c", "copy"]
    command(join + ["-movflags", "+faststart", str(partial)], cwd=scratch)
    try:
        compression = ({"profile": "compacto", "applied": True, "passes": 1,
                        "after_bytes": partial.stat().st_size, "codec": "h264"}
                       if compact_once else compress(partial, options.compression))
    except (OSError, ValueError, StopIteration, sp.SubprocessError) as error:
        compression = {"profile": options.compression, "applied": False,
                       "reason": f"Compressão falhou: {type(error).__name__}"}
    partial.replace(destination)
    insertion = None
    if inserts:
        shot, (path, at) = next(iter(inserts.items()))
        if path in pending_assets:
            insertion = {"shot": shot, "offset": at, "at": sum(b-a for a, b, _ in shots[:shot]) + at,
                         "id": pending_assets[path].digest, "label": pending_assets[path].label, "path": str(path)}
    return {"accents": list(accents.values()), "broll": [asset.name for asset, _ in inserts.values()],
            "visual_insert": insertion,
            "visual_background": {"mode": backdrop_mode, "shots": background_shots,
                                  "asset": background.key if background and background_shots else None},
            "visual_credits": list(visual_credits.values()),
            "transition": options.transition, "dissolves": blends, "sound_cues": cues, "compression": compression,
            "video_encoder": video_encoder[1],
            "jcuts": jcuts, "punches": punches, "run_gains_db": gains, "voice_polish": options.voice_polish,
            "music": Path(music).name if music else None}


def process(source, folder, options, log, *, screening=None, staging_dir=None, on_review=None, recording=None, on_export=None):
    from compression import PRECOMPRESSION_BYTES, prepare_source

    original = source.resolve()
    if not options.render or not options.precompress or original.stat().st_size < PRECOMPRESSION_BYTES:
        return _process(original, folder, options, log, screening, staging_dir, on_review, recording, original, on_export)
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".edicao-", dir=folder) as directory:
        try:
            editing = prepare_source(original, Path(directory), log)
        except (OSError, ValueError, StopIteration, sp.SubprocessError):
            log("Não foi possível preparar uma cópia compacta. Editando o original.")
            editing = original
        return _process(editing, folder, options, log, screening, staging_dir, on_review, recording, original, on_export)


def _process(source, folder, options, log, screening, staging_dir, on_review, recording, original_source, on_export):
    from dataclasses import replace

    folder.mkdir(parents=True, exist_ok=True)
    source = media_for_seeking(source, folder / "midia-revisao.mp4")
    total, audio = probe(source)
    log(f"Analisando {source.name} ({total / 60:.1f} min)")
    if options.auto_face and not options.face:
        face = detect_facecam(source, total)
        options = replace(options, face=face)
        log(f"Facecam: {face or 'sem rosto recorrente no canto; usando gameplay'}")
    if options.face and not options.game:
        options = replace(options, game=gameplay_region(options.face))
    if options.style == "all" and not options.face:
        options = replace(options, style="game")
        log("Exportação sem facecam: gerando uma versão de gameplay.")
    handpicked = bool(options.manual and options.keep_manual_edges)
    signals = [] if handpicked else inspect(source, total, audio, options.face)
    selected = plan(signals, total, options)
    transcript_path = None
    method = "manual" if options.manual else "relative_audio_and_motion"
    if recording and audio and not options.manual:
        from recording_analysis import select
        picks, transcript_path, shortlist = select(source, folder, total, signals, options, *recording, log)
        if picks:
            selected = picks
            method = "recording_transcript_audio_motion"
    editorial_signals = {}
    if handpicked:
        for low, high in options.manual:
            offset = int(low // 2) * 2
            editorial_signals[(low, high)] = (inspect(source, high - offset, audio, options.face, start=offset),
                                              offset)
    report = {"schema": 1, "source": str(source if source.parent == folder else original_source), "original_source": str(original_source),
              "duration": total, "unit": "seconds",
              "method": method,
              "facecam": options.face, "gameplay": options.game, "clips": []}
    if transcript_path is not None:
        report["transcript"] = transcript_path.name
        report["transcript_readable"] = "transcricao.txt"
        report["recording_selection"] = [
            {key: pick[key] for key in ("start", "end", "av_score", "semantic") if key in pick}
            for pick in shortlist
        ]
    report_path = folder / "cortes.json"
    cleanup = options.cleanup
    prepared = []
    styles = ("dynamic", "split", "reaction") if options.style == "all" else (options.style,)
    for index, parts in enumerate(selected, 1):
        log(f"Edição {index}/{len(selected)}: preparando os trechos selecionados.")
        shared_words = None
        if audio and cleanup.speech and not options.manual:
            log("Transcrevendo a fala para ajustar os cortes às frases.")
            shared_words = transcribe(source, max(0, parts[0][0] - 3), min(total, parts[-1][1] + 3),
                                      language=options.speech_language)
            parts = refine_montage(parts, shared_words, total)
        kept, removals, transcript = [], [], []
        range_signals = {}
        for low, high in parts:
            words = ([w for w in shared_words if w[0] < high and w[1] > low]
                     if shared_words is not None else [])
            if audio and shared_words is None and (cleanup.fillers or cleanup.repeats or cleanup.speech_gaps
                                                   or options.hook or options.effects_model or options.broll_dir or options.broll_assets
                                                   or options.visual_library or screening
                                                   or (options.render and options.captions)):
                log(f"Transcrevendo o trecho de {low:.1f}s a {high:.1f}s.")
                words = transcribe(source, low, high, language=options.speech_language)
            edits = list(transcript_edits(words, cleanup))
            if options.trim_inactive:
                bins = inspect(source, high-low, audio, options.face, start=low, normalized=False)
                edits.extend(quiet_live_edits(low, high, bins, words, cleanup.noise))
            else:
                if cleanup.speech_gaps:
                    edits.extend(speech_gap_edits(words, cleanup))
                if audio and cleanup.silence:
                    edits.extend(audio_silences(source, low, high, cleanup))
            if options.manual and options.keep_manual_edges:
                edits = [edit for edit in edits if edit[0] > low + .20 and edit[1] < high - .20]
            ranges, removed = clean_ranges(low, high, edits, words)
            kept.extend(ranges)
            for segment in ranges:
                range_signals[segment] = editorial_signals.get((low, high), (signals, 0))
            removals.extend(removed)
            transcript.extend(words)
        by_style = {style: [shot for low, high in kept
                            for shot in layouts(range_signals[(low, high)][0], low, high,
                                                replace(options, style=style), transcript,
                                                signal_offset=range_signals[(low, high)][1])]
                    for style in styles}
        spoken = [word for word in transcript if any(a <= (word[0] + word[1]) / 2 < b for a, b in kept)]
        if options.render and options.captions:
            log(f"Legendas: {len(spoken)} palavras reconhecidas." if spoken else
                "Legendas: nenhuma fala reconhecida no trecho.")
        log(f"Edição: {len(kept)} trecho(s), {len(removals)} remoção(ões).")
        hook = " ".join(options.hook_text.split())[:64]
        if not hook and options.hook:
            hook = opening_phrase(spoken, kept[0][0])
        creative = {}
        cut_options = options
        if options.effects_model and options.render and spoken:
            from creative_studio import EFFECTS, propose
            creative = propose(options.effects_model, " ".join(word for _, _, word in spoken), hook)
            if creative["generated"]:
                effect = EFFECTS[creative["effect"]]
                cut_options = replace(options, polish=effect != "corte", transition=effect)
        report["clips"].append({
            "parts": [dict(start=a, end=b, score=score(range_signals[(a, b)][0], a, b, range_signals[(a, b)][1]))
                      for a, b in kept],
            "removed": removals,
            "caption_words": len(spoken) if options.render and options.captions else 0,
            "hook": hook,
            "creative": creative,
            "layouts": [dict(start=a, end=b, style=s) for a, b, s in by_style[styles[0]]],
            "variants": {key: {"layouts": [dict(start=a, end=b, style=s) for a, b, s in shots]}
                         for key, shots in by_style.items()}
        })
        prepared.append((by_style, spoken, hook, cut_options))
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"{len(prepared)} corte(s) planejado(s) em {folder.name}")
    if not options.render:
        return
    for index, (by_style, words, hook, cut_options) in enumerate(prepared, 1):
        entry = report["clips"][index - 1]
        for style, shots in by_style.items():
            suffix = f"_{style}" if len(by_style) > 1 else ""
            destination = folder / f"clip_{index:02}{suffix}.mp4"
            log(f"Renderizando {destination.name} ({style}, {len(shots)} plano(s)).")
            variant = entry["variants"][style]
            if options.review_visuals:
                from visual_review import prepare_preview
                prepare_preview(original_source, folder, shots, words, cut_options, hook, screening)
                log("Prévia pronta. Revise as inserções antes de exportar.")
                continue
            publish = (staging_dir or folder) / f".review-{folder.name}-{destination.name}"
            try:
                variant["finishing"] = render_clip(source, publish, shots,
                                                   words if options.captions else [], cut_options,
                                                   hook, timing_words=words)
                if screening is not None:
                    from final_screen import evaluate
                    log(f"Revisão técnica e editorial: {destination.name}.")
                    model, threshold, prior = screening
                    prior = {**prior, "speech_language": options.speech_language}
                    verdict = evaluate(publish, FF, command, sum(b - a for a, b, _ in shots),
                                       words, model, threshold, prior)
                    verdict["duration"] = sum(b - a for a, b, _ in shots)
                    verdict["source"] = str(original_source)
                    verdict["visual_credits"] = variant["finishing"]["visual_credits"]
                    verdict["studio_transcript"] = verdict.pop("review_transcript", " ".join(word for _, _, word in words)[:1450])
                    offset = prior.get("origin_offset", 0)
                    verdict["ranges"] = [(part["start"] + offset, part["end"] + offset) for part in entry["parts"]]
                    if "origin_url" in prior:
                        verdict["origin_url"] = prior["origin_url"]
                    variant["screening"] = verdict
                    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                    if verdict["status"] != "ready":
                        if on_review:
                            on_review(destination, None, verdict, words, hook)
                        log(f"Descartado depois da edição: {verdict['score']}/100 ({verdict['reason']}).")
                        continue
                    publish.replace(destination)
                    if on_export:
                        on_export(destination)
                    if on_review:
                        on_review(destination, destination, verdict, words, hook)
                    log(f"Aprovado depois da edição: {verdict['score']}/100 ({verdict.get('review_engine', 'regras_locais')}).")
                else:
                    publish.replace(destination)
                    if on_export:
                        on_export(destination)
            finally:
                publish.unlink(missing_ok=True)
            variant["output"] = destination.name
            if options.save_review:
                try:
                    from review import export_review
                    review_path = destination.with_suffix(".otio")
                    export_review(source if source.parent == folder else original_source, shots, review_path, audio)
                    entry["variants"][style]["review"] = review_path.name
                except (ImportError, RuntimeError, OSError) as error:
                    log(f"Timeline de revisão indisponível: {error}")
            entry.setdefault("output", destination.name)
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            log(f"Pronto: {destination}")
    return report


def twitch_source(value):
    parsed = urlparse(value if "://" in value else f"https://www.twitch.tv/{value}")
    if parsed.scheme not in ("https", "http") or parsed.netloc.lower() not in ("twitch.tv", "www.twitch.tv"):
        raise ValueError("Informe um canal ou VOD público da Twitch.")
    path = parsed.path.strip("/")
    if not re.fullmatch(r"(?:videos/[0-9]+|[a-zA-Z0-9_]{1,25})", path):
        raise ValueError("Canal ou ID de VOD inválido.")
    return "https://www.twitch.tv/" + path, path.startswith("videos/")


X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
KICK_HOSTS = {"kick.com", "www.kick.com"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com"}


def live_source(value):
    parsed = urlparse(value if "://" in value or "/" not in value else f"https://{value}")
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if host in YOUTUBE_HOSTS and parsed.scheme in ("https", "http"):
        video_id = (parse_qs(parsed.query).get("v", [""])[0] if path == "/watch" else
                    path.rsplit("/", 1)[-1] if host == "youtu.be" or path.startswith(("/live/", "/shorts/")) else "")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            live = path.startswith("/live/")
            return f"https://www.youtube.com/{'live/' if live else 'watch?v='}{video_id}", not live
        channel = re.fullmatch(r"(/@[\w.-]{1,100}|/channel/UC[A-Za-z0-9_-]{22})(?:/live)?", path)
        if channel and host != "youtu.be":
            return f"https://www.youtube.com{channel[1]}/live", False
        raise ValueError("No YouTube, use @canal, /live/ID ou a URL do vídeo gravado.")
    if host in TIKTOK_HOSTS and parsed.scheme in ("https", "http"):
        channel = re.fullmatch(r"(/@[A-Za-z0-9._]{1,48})(?:/live)?", path)
        if channel:
            return f"https://www.tiktok.com{channel[1]}/live", False
        if re.fullmatch(r"/@[A-Za-z0-9._]{1,48}/video/\d+", path):
            return f"https://www.tiktok.com{path}", True
        raise ValueError("No TikTok, informe a URL completa do canal, live ou vídeo público.")
    if host in KICK_HOSTS:
        path = parsed.path.strip("/")
        match = re.fullmatch(r"([A-Za-z0-9_-]{1,48})(?:/videos/([a-fA-F0-9-]{36}))?", path)
        if parsed.scheme not in ("https", "http") or match is None:
            raise ValueError("Na Kick, cole o link do canal ou de um VOD público.")
        return "https://kick.com/" + path.lower(), bool(match[2])
    if parsed.netloc.lower() in X_HOSTS:
        path = parsed.path.rstrip("/")
        if parsed.scheme not in ("https", "http") or not re.fullmatch(
                r"/(?:i/broadcasts/[a-zA-Z0-9]+|(?:i/web|[a-zA-Z0-9_]{1,20})/status/\d+(?:/video/\d+)?)", path):
            raise ValueError("No X, cole o link público da transmissão ou da publicação que contém a live de vídeo.")
        return "https://x.com" + path, False
    return twitch_source(value)


class BroadcastEnded(Exception):
    """The provider confirmed the broadcast ended."""


def extractor_live_media(python, url, capture_height=None):
    is_x = urlparse(url).hostname in X_HOSTS
    platform = "X" if is_x else "TikTok"
    try:
        raw = command([python, "-m", "yt_dlp", "--ignore-config", "--compat-options", "no-certifi",
                       "--no-playlist", "--no-warnings",
                       "--socket-timeout", "12", "--extractor-retries", "0", "--dump-single-json",
                       "-f", f"b[height<={capture_height}]" if capture_height else "b[height<=720]/b",
                       "--", url], timeout=25)
    except RuntimeError as error:
        if is_x and "broadcast no longer exists" in str(error).casefold():
            raise BroadcastEnded("O X informou que esta transmissão não está mais disponível.") from error
        raise
    info = json.loads(raw)
    if info.get("live_status") in {"post_live", "was_live"} or info.get("was_live"):
        raise BroadcastEnded(f"A plataforma {platform} informou que a transmissão já terminou.")
    if not (info.get("is_live") or info.get("live_status") == "is_live"):
        if info.get("live_status") == "is_upcoming":
            raise RuntimeError(f"Transmissão agendada no {platform}. Aguardando início.")
        raise RuntimeError(f"Sem vídeo ao vivo disponível neste link do {platform}.")
    media = info.get("url", "")
    if urlparse(media).scheme not in ("https", "http"):
        raise RuntimeError(f"Sem endereço de mídia HTTP utilizável no {platform}.")
    headers = [f"{k}: {v}\r\n" for k, v in (info.get("http_headers") or {}).items()
               if re.fullmatch(r"[A-Za-z0-9-]+", k) and isinstance(v, str) and not re.search(r"[\r\n]", v)]
    return ["-rw_timeout", "20000000", "-tls_verify", "1",
            "-protocol_whitelist", "http,https,tcp,tls,crypto",
            *(["-headers", "".join(headers)] if headers else []), "-i", media]


def streamlink_cli(python):
    bootstrap = "import truststore; truststore.inject_into_ssl(); from streamlink_cli.main import main; main()"
    return [python, "-c", bootstrap]


def fetch_vod(python, url, folder, *, max_bytes=None, stop=None):
    host = urlparse(url).hostname
    mp4 = folder / "vod.mp4"
    ts = folder / "vod.ts"
    download = [python, "-m", "yt_dlp", "--ignore-config", "--compat-options", "no-certifi",
                "--no-playlist", "--match-filter", "!is_live", "--socket-timeout", "15",
                "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                "--remux-video", "mp4", "-o", str(mp4), "--", url]
    if max_bytes:
        download[3:3] = ["--max-filesize", str(max_bytes)]

    def transfer(args, target):
        with (folder / "download.log").open("ab") as log:
            with sp.Popen(args, stdout=log, stderr=log, stdin=sp.DEVNULL, **runtime.child_options()) as child:
                try:
                    deadline = time.monotonic() + 21600
                    while child.poll() is None:
                        if stop and stop.is_set():
                            raise InterruptedError("Download interrompido.")
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Tempo limite do download atingido.")
                        if not capture_space(folder):
                            raise OSError("Volume com menos de 256 MiB livres.")
                        if max_bytes and sum(file.stat().st_size for file in folder.glob("vod*")
                                             if file.is_file()) > max_bytes:
                            raise OSError("Limite de espaço da captura atingido.")
                        try:
                            child.wait(timeout=1)
                        except sp.TimeoutExpired:
                            pass
                    if child.returncode or not target.is_file():
                        raise RuntimeError(f"Download indisponível. Consulte {folder / 'download.log'}.")
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait()
        probe(target)
        return target

    if host in YOUTUBE_HOSTS | TIKTOK_HOSTS:
        return transfer(download, mp4)
    try:
        return transfer(streamlink_cli(python) + ["--loglevel", "error", "--output", str(ts),
                                                 url, "720p,480p,best"], ts)
    except (RuntimeError, ValueError):
        if host not in KICK_HOSTS:
            raise
        # The primary transport can fail while yt-dlp resolves the same public replay.
        ts.unlink(missing_ok=True)
        return transfer(download, mp4)


CAPTURE_RESERVE = 256 * 1024 * 1024


def capture_space(folder):
    return shutil.disk_usage(folder).free >= CAPTURE_RESERVE


def capture(python, url, folder, minutes, schedule, stop, log, wait_minutes=0, segment_seconds=120,
            *, continuous=False, catchup=False, offline_seconds=45, on_state=None, capture_height=None,
            discard_short=False, on_ended=None):
    """Wait for a live source and optionally return to watching between broadcasts."""
    ready_by = time.monotonic() + wait_minutes * 60
    deadline = None
    last_media = None
    attempt = 0
    while not stop.is_set():
        if not capture_space(folder):
            reason = f"Espaço insuficiente para captura · mínimo de {CAPTURE_RESERVE // 1024**2} MiB livres"
            log(f"{reason}: {folder}")
            if on_state:
                on_state(reason)
            if not continuous:
                raise OSError(reason)
            stop.wait(45)
            continue
        if on_state:
            on_state("Verificando")
        attempt += 1
        target = folder / f"conexao_{attempt:03}"
        target.mkdir()
        started = time.monotonic()
        seconds = (max(1, round(deadline - started)) if deadline else (minutes * 60 if minutes else None))
        try:
            found = capture_once(python, url, target, seconds, schedule, stop, log, segment_seconds,
                                 catchup=catchup and (last_media is None or started - last_media >= 180),
                                 on_state=on_state, capture_height=capture_height, discard_short=discard_short)
        except BroadcastEnded as error:
            log(str(error))
            if on_ended and not stop.is_set():
                on_ended()
            return
        except (RuntimeError, ValueError, OSError, sp.TimeoutExpired) as error:
            found = False
            with (target / "captura.log").open("a", encoding="utf-8") as diagnostics:
                diagnostics.write(str(error) + "\n")
        now = time.monotonic()
        if found:
            last_media = now
            if minutes and deadline is None:
                deadline = started + minutes * 60
        if stop.is_set() or (deadline and now >= deadline - 2):
            return
        retry_until = last_media + 70 if last_media is not None else ready_by
        if last_media is not None and now >= retry_until and not found:
            if on_ended:
                on_ended()
            if continuous:
                last_media = None
        if continuous:
            # Empty attempts contain diagnostics only; retain the current one without
            # letting idle checks create directories indefinitely.
            previous = folder / f"conexao_{attempt - 1:03}"
            ledger = previous / "captura.csv"
            if (previous.is_dir() and (not ledger.exists() or not ledger.stat().st_size)
                    and not any(p.suffix == ".ts" for p in previous.iterdir())):
                for name in ("captura.log", "captura.csv"):
                    (previous / name).unlink(missing_ok=True)
                if not any(previous.iterdir()):
                    previous.rmdir()
            log(f"{'Reconectando' if last_media and now < retry_until else 'Monitorando canal'}: {url}")
            delay = 20 if last_media and now < retry_until else offline_seconds
            if on_state:
                on_state("Reconectando" if delay == 20 else
                         f"Aguardando live · verifica em {delay // 3600} h" if delay >= 3600 else
                         "Aguardando live")
            stop.wait(delay)
            continue
        if now >= retry_until:
            if not found and last_media is None:
                log(f"Nenhum vídeo ao vivo para {url}. Consulte {target / 'captura.log'}")
            else:
                log(f"Captura encerrada: {url}")
            return
        log(f"{'Reconectando' if last_media is not None else 'Aguardando live'}: {url}")
        stop.wait(min(20, max(0, retry_until - now)))


def capture_once(python, url, folder, seconds, schedule, stop, log, segment_seconds, *,
                 catchup=False, on_state=None, capture_height=None, discard_short=False):
    """Own the capture processes and send only segments closed by FFmpeg."""
    found = False
    position = 0
    fragment = b""
    index = folder / "captura.csv"
    deadline = time.monotonic() + seconds + 40 if seconds else float("inf")

    def queue_finished():
        nonlocal found, position, fragment
        if not index.exists():
            return
        with index.open("rb") as manifest:
            manifest.seek(position)
            rows = (fragment + manifest.read()).split(b"\n")
            position = manifest.tell()
        fragment = rows.pop()
        for row in csv.reader(line.decode("utf-8").strip() for line in rows):
            if len(row) != 3 or not re.fullmatch(r"live_\d+\.ts", row[0]):
                continue
            path = folder / row[0]
            if path.exists():
                minimum = 2 if segment_seconds <= 30 else 8
                if path.stat().st_size and float(row[2]) - float(row[1]) >= minimum:
                    if not found:
                        from compression import metadata
                        try:
                            _, _, (width, height, _), _ = metadata(path)
                            log(f"Qualidade da captura: {width} × {height}.")
                        except (OSError, ValueError, KeyError, StopIteration, sp.SubprocessError):
                            pass
                    found = True
                    schedule(path, folder / path.stem)
                elif discard_short:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as error:
                        log(f"Limpeza de bloco curto {path.name}: {error}")

    host = urlparse(url).netloc.lower()
    direct = host in X_HOSTS | TIKTOK_HOSTS
    dvr = catchup and not direct
    latency = (["--hls-live-restart"] if dvr else
               ["--twitch-low-latency"] if host == "www.twitch.tv" else [])
    quality = runtime.active.quality
    if capture_height:
        quality = live_variant_order(capture_height)
    input_args = extractor_live_media(python, url, capture_height) if direct else ["-i", "pipe:0"]
    if stop.is_set():
        return False
    if dvr:
        log(f"Recuperando o início ainda disponível na janela pública de {url}.")
    with (folder / "captura.log").open("wb") as errors:
        sl = None if direct else sp.Popen(streamlink_cli(python) + ["--stdout", *latency,
                                      "--stream-segment-threads", str(1 if runtime.active.low_priority else runtime.active.dvr_threads),
                                      "--stream-segment-timeout", "15", "--stream-timeout", "25",
                                      "--loglevel", "warning", url, quality],
                                     stdout=sp.PIPE, stderr=errors, **runtime.child_options(hide=True))
        ff = None
        try:
            ff = sp.Popen((FF[:-1] if direct else FF) + input_args + ["-map", "0:v:0", "-map", "0:a:0?"]
                          + (["-t", str(seconds)] if seconds else [])
                          + ["-c", "copy", "-f", "segment",
                                "-segment_time", str(segment_seconds), "-reset_timestamps", "1",
                                "-segment_list", index.name, "-segment_list_type", "csv",
                                "live_%04d.ts"], stdin=sp.PIPE if direct else sl.stdout, cwd=folder, stderr=errors, **runtime.child_options(hide=True))
            if sl is not None:
                sl.stdout.close()
            last_data = time.monotonic()
            signature = None
            while ff.poll() is None and not stop.wait(2) and time.monotonic() < deadline:
                queue_finished()
                if not capture_space(folder):
                    log(f"Captura interrompida para preservar espaço em {folder}.")
                    break
                segment = max(folder.glob("live_*.ts"), default=None)
                if segment is not None:
                    try:
                        current = (segment.name, segment.stat().st_size)
                    except FileNotFoundError:
                        current = None
                    if current is not None and current[1] > 0 and current != signature:
                        if signature is None:
                            log(f"Ao vivo · recebendo vídeo de {url}")
                            if on_state:
                                on_state("Ao vivo · capturando")
                        last_data, signature = time.monotonic(), current
                if time.monotonic() - last_data > 65:
                    log(f"Sem dados de vídeo na conexão: {url}")
                    break
        finally:
            if sl is not None:
                sl.stdout.close()
                if sl.poll() is None:
                    sl.terminate()
                sl.wait()
            if ff is not None:
                if direct and ff.poll() is None:
                    try:
                        ff.stdin.write(b"q\n")
                        ff.stdin.flush()
                    except OSError:
                        pass
                try:
                    ff.wait(timeout=12)
                except sp.TimeoutExpired:
                    ff.kill()
                    ff.wait()
                if ff.stdin is not None:
                    ff.stdin.close()
    queue_finished()
    return found
