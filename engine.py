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
from editorial import Cleanup, clean_ranges, refine_montage, silence_edits, speech_gap_edits, transcript_edits
from facecam import estimate, gameplay_region
from finishing import accent_shots, caption_groups, pick_broll
from effects_bank import edge_transition, render_cues

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


def command(args, **kwargs):
    result = sp.run(args, capture_output=True, **kwargs)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(message[:1000] or str(args[0]))
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


def inspect(source, duration, audio, face=""):
    """Two-second samples. No rendering or speech model needed for this pass."""
    pcm = array.array("h")
    if audio:
        pcm.frombytes(command(FF + ["-threads", "2", "-i", str(source), "-vn", "-ac", "1",
                                    "-ar", "800", "-f", "s16le", "pipe:1"]))
    width, height = 64, 36
    size = width * height
    frames = command(FF + ["-threads", "2", "-filter_threads", "1", "-i", str(source),
                          "-an", "-vf", f"fps=1/2,scale={width}:{height},format=gray",
                          "-c:v", "rawvideo", "-threads", "1", "-f", "rawvideo", "pipe:1"])
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
    baselines = [max(floor, statistics.median(p[k] for p in pairs))
                 for k, floor in enumerate((100, 2, 2))]
    return [tuple(min(5, value / baseline) for value, baseline in zip(pair, baselines)) for pair in pairs]


def score(signals, start, end):
    bins = signals[int(start // 2):math.ceil(end / 2)]
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


def layout_graph(style, options):
    def fit(region, width, height):
        return (crop(region) + f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2,setsar=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101522")
    def game_canvas(source, target):
        return (f"{source}{crop(options.game)}split=2[back][play];"
                f"[back]scale=180:320:force_original_aspect_ratio=increase:force_divisible_by=2,"
                f"crop=180:320,gblur=sigma=12,drawbox=c=black@0.24:t=fill,"
                f"scale={WIDTH}:{HEIGHT},setsar=1[blur];"
                f"[play]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2,setsar=1[active];"
                f"[blur][active]overlay=(W-w)/2:(H-h)/2{target}")
    def fill(region, height):
        return (crop(region) + f"scale={WIDTH}:{height}:force_original_aspect_ratio=increase:"
                f"force_divisible_by=2,crop={WIDTH}:{height},setsar=1")
    focus = options.close_focus
    face_fill = (crop(options.face) + f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:"
                 f"force_divisible_by=2,crop={WIDTH}:{HEIGHT}:(iw-ow)*{focus}:(ih-oh)/2,setsar=1")
    if style == "gamecam":
        x = "W-w-34" if options.corner == "direito" else "34"
        circle = ("format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                  "a='if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2-2)*(W/2-2)),255,0)'")
        camera = (crop(options.face) + "scale=196:196:force_original_aspect_ratio=increase:"
                  f"force_divisible_by=2,crop=196:196:(iw-ow)*{focus}:(ih-oh)/2,setsar=1," + circle)
        return (f"[0:v]split=2[f][g];{game_canvas('[g]', '[main]')};"
                f"[f]{camera}[cam];[main][cam]overlay={x}:246[base]")
    if style == "split":
        if options.look == "shorts":
            return (f"[0:v]split=2[f][g];[f]{fill(options.face, 500)}[top];"
                    f"[g]{fill(options.game, 780)}[bottom];[top][bottom]vstack[base]")
        return (f"[0:v]split=2[f][g];[f]{fit(options.face, WIDTH, 440)}[top];"
                f"[g]{fit(options.game, WIDTH, 840)}[bottom];[top][bottom]vstack[base]")
    if style == "reaction":
        x = "W-w-28" if options.corner == "direito" else "28"
        return (f"[0:v]split=2[f][g];[f]{face_fill}[main];"
                f"[g]{fit(options.game, 272, 156)},drawbox=color=white@0.8:t=2[pip];"
                f"[main][pip]overlay={x}:92[base]")
    if style == "face":
        return f"[0:v]{face_fill}[base]"
    return game_canvas("[0:v]", "[base]")


def layouts(signals, start, end, options, words=()):
    if not options.face:
        return [(start, end, "game")]
    if options.style != "dynamic":
        return [(start, end, options.style)]
    segments = []
    point = start
    while point < end - .01:
        stop = end if end - point < 8 else point + 4
        bins = signals[int(point // 2):math.ceil(stop / 2)]
        activity = [statistics.mean(values) for values in zip(*bins)] if bins else []
        audio, motion, cam = (activity + [0, 0, 0])[:3]
        reaction = any(point <= a < stop and ("!" in text or text.casefold().strip("!?.,") in
                       {"caramba", "nossa", "mano", "wow", "eita"}) for a, _, text in words)
        if (cam >= 1.45 and audio >= 1.2 and motion < cam * 1.4) or (
                reaction and audio >= 1.4 and cam >= 1.05):
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


def transcribe(source, start, end, model="base"):
    import numpy as np
    from faster_whisper import WhisperModel

    pcm = command(FF + ["-ss", str(start), "-i", str(source), "-t", str(end - start),
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"])
    if not pcm:
        return []
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    with MODEL_LOCK:
        if model not in MODELS:
            MODELS[model] = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=2,
                                         download_root=str(Path(__file__).parent / "models"))
        segments, _ = MODELS[model].transcribe(samples, word_timestamps=True, vad_filter=True,
                                               beam_size=1 if model == "tiny" else 5)
        return [(start + w.start, start + w.end, w.word.strip())
                for s in segments for w in (s.words or []) if w.word.strip()]


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


def subtitles(path, words, start, end, style, look="classic", hook="", opening=None):
    y = (562 if look == "shorts" else 495) if style == "split" else 1035
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,48,&H0000DEFF,&H00FFFFFF,&H00101218,&H60000000,-1,0,0,0,100,100,0,0,1,4,1,5,50,50,40,1
Style: Hook,Arial,44,&H00FFFFFF,&H00FFFFFF,&H00131824,&H00131824,-1,0,0,0,100,100,0,0,3,11,0,5,106,106,30,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
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
    from audio_finish import loudness_filter, make_mix, program

    scratch = destination.with_suffix("")
    scratch.mkdir()
    source = media_for_seeking(source, scratch / "source.mp4")
    pieces = []
    accents = accent_shots(shots) if options.polish else {}
    inserts = pick_broll(options.broll_dir, shots, timing_words if timing_words is not None else words)
    audio = probe(source)[1]
    elapsed = 0.0
    frame_counts = []
    punches = []
    for index, (start, end, style) in enumerate(shots):
        frame_start = round(elapsed * 30)
        elapsed += end - start
        frames = max(1, round(elapsed * 30) - frame_start)
        frame_counts.append(frames)
        name = f"p{len(pieces):03}.mp4"
        graph = layout_graph(style, options)
        layer = "[base]"
        inputs = []
        opening_punch = index == 0 and (style == "face" or (style == "split" and hook))
        highlight_punch = index in accents and style == "face"
        if options.polish and options.transition == "zoom" and end - start >= .9 and (opening_punch or highlight_punch):
            amount = .09 if highlight_punch else .04
            punches.append({"shot": index + 1, "zoom": 1+amount})
            graph += (f";{layer}fps=30,zoompan=z='1+{amount}*(1-exp(-on/4))':"
                      "x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=720x1280:fps=30[punch]")
            layer = "[punch]"
        if options.polish and options.transition == "linha" and index in accents:
            graph += edge_transition(layer, "[transition]")
            layer = "[transition]"
        if index in inserts:
            asset, at = inserts[index]
            inputs = (["-loop", "1"] if asset.suffix.lower() in {".png", ".jpg"} else
                      ["-stream_loop", "-1"]) + ["-i", str(asset)]
            graph += (";[1:v]trim=duration=1.15,setpts=PTS-STARTPTS,"
                      "scale=290:164:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                      "pad=290:164:(ow-iw)/2:(oh-ih)/2,drawbox=c=white@0.7:t=2,format=yuva420p,"
                      "fade=t=in:d=0.10:alpha=1,fade=t=out:st=1.02:d=0.12:alpha=1,"
                      f"setpts=PTS+{at:.3f}/TB[detail];"
                      f"{layer}[detail]overlay=W-w-48:680:eof_action=pass:"
                      f"enable='between(t,{at:.3f},{at+1.15:.3f})'[inserted]")
            layer = "[inserted]"
        if words or hook:
            subtitles(scratch / "legend.ass", words, start, end, style, options.look, hook, shots[0][0])
            graph += f";{layer}ass=legend.ass[out]"
        else:
            graph += f";{layer}null[out]"
        command(FF + ["-y", "-threads", "2", "-ss", str(start), "-i", str(source),
                      *inputs, "-filter_complex_threads", "1", "-filter_complex", graph,
                      "-map", "[out]", "-an", "-r", "30", "-frames:v", str(frames)]
                + encoder() + ENC + [name], cwd=scratch)
        pieces.append(name)
    listing = scratch / "join.txt"
    listing.write_text("".join(f"file '{name}'\n" for name in pieces), encoding="ascii")
    partial = destination.with_suffix(".partial.mp4")
    join = FF + ["-y", "-f", "concat", "-safe", "1", "-i", listing.name]
    cues = [(time, options.sfx if options.sfx != "auto" else
             {"face": "impacto", "gamecam": "radio"}.get(shots[index][2], "whoosh"))
            for index, time in accents.items()] if options.sfx != "nenhum" else []
    jcuts, gains = [], []
    if audio or options.music or cues:
        duration = sum(frame_counts) / 30
        if audio:
            jcuts, gains = program(lambda args: command(FF + args), source, shots, frame_counts,
                                   scratch / "program.wav", options.jcut_ms, options.voice_polish)
        else:
            command(FF + ["-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                          "-t", str(duration), "program.wav"], cwd=scratch)
        if cues:
            render_cues(scratch / "cues.wav", duration, cues, options.sfx_peak)
        if cues or options.music or options.voice_polish:
            music = str(Path(options.music).resolve()) if options.music else ""
            make_mix(FF, command, scratch, duration, options.voice_polish, music, options.music_db, bool(cues))
            join += ["-i", "mix.wav", "-map", "1:a:0"]
            if options.voice_polish:
                join += ["-af", loudness_filter(FF, scratch), "-ar", "48000"]
        else:
            join += ["-i", "program.wav", "-map", "1:a:0"]
        join += ["-map", "0:v:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        join += ["-c", "copy"]
    command(join + ["-movflags", "+faststart", str(partial)], cwd=scratch)
    partial.replace(destination)
    for name in [*pieces, "join.txt", "legend.ass", "cues.wav", "program.wav", "mix.wav", "source.mp4"]:
        (scratch / name).unlink(missing_ok=True)
    scratch.rmdir()
    return {"accents": list(accents.values()), "broll": [asset.name for asset, _ in inserts.values()],
            "transition": options.transition, "sound_cues": cues,
            "jcuts": jcuts, "punches": punches, "run_gains_db": gains, "voice_polish": options.voice_polish,
            "music": Path(options.music).name if options.music else None}


def process(source, folder, options, log):
    from dataclasses import replace

    folder.mkdir(parents=True, exist_ok=True)
    original_source = source.resolve()
    source = media_for_seeking(original_source, folder / "midia-revisao.mp4")
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
    signals = inspect(source, total, audio, options.face)
    selected = plan(signals, total, options)
    report = {"schema": 1, "source": str(source), "original_source": str(original_source),
              "duration": total, "unit": "seconds",
              "method": "manual" if options.manual else "relative_audio_and_motion",
              "facecam": options.face, "gameplay": options.game, "clips": []}
    report_path = folder / "cortes.json"
    cleanup = options.cleanup
    prepared = []
    styles = ("dynamic", "split", "reaction") if options.style == "all" else (options.style,)
    for index, parts in enumerate(selected, 1):
        log(f"Preparando montagem {index}/{len(selected)}")
        shared_words = None
        if audio and cleanup.speech and not options.manual:
            shared_words = transcribe(source, max(0, parts[0][0] - 3), min(total, parts[-1][1] + 3))
            parts = refine_montage(parts, shared_words, total)
        kept, removals, transcript = [], [], []
        for low, high in parts:
            words = ([w for w in shared_words if w[0] < high and w[1] > low]
                     if shared_words is not None else [])
            if audio and shared_words is None and (cleanup.fillers or cleanup.repeats or cleanup.speech_gaps
                                                   or options.hook or options.broll_dir
                                                   or (options.render and options.captions)):
                words = transcribe(source, low, high)
            edits = list(transcript_edits(words, cleanup))
            if cleanup.speech_gaps:
                edits.extend(speech_gap_edits(words, cleanup))
            if audio and cleanup.silence:
                edits.extend(audio_silences(source, low, high, cleanup))
            ranges, removed = clean_ranges(low, high, edits, words)
            kept.extend(ranges)
            removals.extend(removed)
            transcript.extend(words)
        by_style = {style: [shot for low, high in kept
                            for shot in layouts(signals, low, high, replace(options, style=style), transcript)]
                    for style in styles}
        spoken = [word for word in transcript if any(a <= (word[0] + word[1]) / 2 < b for a, b in kept)]
        hook = ""
        if options.hook:
            hook = opening_phrase(spoken, kept[0][0])
        report["clips"].append({
            "parts": [dict(start=a, end=b, score=score(signals, a, b)) for a, b in kept],
            "removed": removals,
            "hook": hook,
            "layouts": [dict(start=a, end=b, style=s) for a, b, s in by_style[styles[0]]],
            "variants": {key: {"layouts": [dict(start=a, end=b, style=s) for a, b, s in shots]}
                         for key, shots in by_style.items()}
        })
        prepared.append((by_style, spoken, hook))
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"{len(prepared)} corte(s) planejado(s) em {folder.name}")
    if not options.render:
        return
    for index, (by_style, words, hook) in enumerate(prepared, 1):
        entry = report["clips"][index - 1]
        for style, shots in by_style.items():
            suffix = f"_{style}" if len(by_style) > 1 else ""
            destination = folder / f"clip_{index:02}{suffix}.mp4"
            finishing = render_clip(source, destination, shots, words if options.captions else [], options,
                                    hook, timing_words=words)
            entry["variants"][style]["output"] = destination.name
            entry["variants"][style]["finishing"] = finishing
            try:
                from review import export_review
                review_path = destination.with_suffix(".otio")
                export_review(source, shots, review_path, audio)
                entry["variants"][style]["review"] = review_path.name
            except (ImportError, RuntimeError, OSError) as error:
                log(f"Timeline de revisão indisponível: {error}")
            entry.setdefault("output", destination.name)
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            log(f"Pronto: {destination}")


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


def live_source(value):
    parsed = urlparse(value if "://" in value or "/" not in value else f"https://{value}")
    if parsed.netloc.lower() in KICK_HOSTS:
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


def x_media(python, url):
    try:
        raw = command([python, "-m", "yt_dlp", "--ignore-config", "--compat-options", "no-certifi",
                       "--no-playlist", "--no-warnings",
                       "--socket-timeout", "12", "--extractor-retries", "0", "--dump-single-json",
                       "-f", "b[height<=720]/b", "--", url], timeout=25)
    except RuntimeError as error:
        if "broadcast no longer exists" in str(error).casefold():
            raise BroadcastEnded("O X informou que esta transmissão não está mais disponível.") from error
        raise
    info = json.loads(raw)
    if info.get("live_status") in {"post_live", "was_live"} or info.get("was_live"):
        raise BroadcastEnded("O X informou que a transmissão já terminou.")
    if not (info.get("is_live") or info.get("live_status") == "is_live"):
        if info.get("live_status") == "is_upcoming":
            raise RuntimeError("Transmissão do X agendada. Aguardando início.")
        raise RuntimeError("O X ainda não retornou uma transmissão de vídeo ao vivo para este link.")
    media = info.get("url", "")
    if urlparse(media).scheme not in ("https", "http"):
        raise RuntimeError("O X não retornou um endereço de mídia HTTP utilizável.")
    headers = [f"{k}: {v}\r\n" for k, v in (info.get("http_headers") or {}).items()
               if re.fullmatch(r"[A-Za-z0-9-]+", k) and isinstance(v, str) and not re.search(r"[\r\n]", v)]
    return ["-rw_timeout", "20000000", "-tls_verify", "1",
            "-protocol_whitelist", "http,https,tcp,tls,crypto",
            *(["-headers", "".join(headers)] if headers else []), "-i", media]


def streamlink_cli(python):
    bootstrap = "import truststore; truststore.inject_into_ssl(); from streamlink_cli.main import main; main()"
    return [python, "-c", bootstrap]


def fetch_vod(python, url, folder):
    path = folder / "vod.ts"
    command(streamlink_cli(python) + ["--loglevel", "error", "--output", str(path),
             url, "720p,480p,best"], timeout=21600)
    return path


def capture(python, url, folder, minutes, schedule, stop, log, wait_minutes=0, segment_seconds=120):
    """Wait for a live source and reconnect briefly if its transport drops."""
    ready_by = time.monotonic() + wait_minutes * 60
    deadline = None
    last_media = None
    attempt = 0
    while not stop.is_set():
        attempt += 1
        target = folder / f"conexao_{attempt:03}"
        target.mkdir()
        started = time.monotonic()
        seconds = (max(1, round(deadline - started)) if deadline else (minutes * 60 if minutes else None))
        try:
            found = capture_once(python, url, target, seconds, schedule, stop, log, segment_seconds)
        except BroadcastEnded as error:
            log(str(error))
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
        if now >= retry_until:
            if not found and last_media is None:
                log(f"Nenhum vídeo ao vivo para {url}. Consulte {target / 'captura.log'}")
            else:
                log(f"Captura encerrada: {url}")
            return
        log(f"{'Reconectando' if last_media is not None else 'Aguardando live'}: {url}")
        stop.wait(min(20, max(0, retry_until - now)))


def capture_once(python, url, folder, seconds, schedule, stop, log, segment_seconds):
    """Own the capture processes and send only segments closed by FFmpeg."""
    seen = set()
    index = folder / "captura.csv"
    deadline = time.monotonic() + seconds + 40 if seconds else float("inf")

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
                minimum = 2 if segment_seconds <= 30 else 8
                if path.stat().st_size and float(row[2]) - float(row[1]) >= minimum:
                    schedule(path, folder / path.stem)

    host = urlparse(url).netloc.lower()
    x = host in X_HOSTS
    latency = [] if host in KICK_HOSTS else ["--twitch-low-latency"]
    input_args = x_media(python, url) if x else ["-i", "pipe:0"]
    if stop.is_set():
        return False
    with (folder / "captura.log").open("wb") as errors:
        sl = None if x else sp.Popen(streamlink_cli(python) + ["--stdout", *latency,
                                      "--loglevel", "warning", url, "480p,360p,best"],
                                     stdout=sp.PIPE, stderr=errors)
        ff = None
        try:
            ff = sp.Popen((FF[:-1] if x else FF) + input_args + ["-map", "0:v:0", "-map", "0:a:0?"]
                          + (["-t", str(seconds)] if seconds else [])
                          + ["-c", "copy", "-f", "segment",
                                "-segment_time", str(segment_seconds), "-reset_timestamps", "1",
                                "-segment_list", index.name, "-segment_list_type", "csv",
                                "live_%04d.ts"], stdin=sp.PIPE if x else sl.stdout, cwd=folder, stderr=errors)
            if sl is not None:
                sl.stdout.close()
            log(f"Capturando {url}")
            last_data = time.monotonic()
            signature = None
            while ff.poll() is None and not stop.wait(2) and time.monotonic() < deadline:
                queue_finished()
                segment = max(folder.glob("live_*.ts"), default=None)
                if segment is not None:
                    current = (segment.name, segment.stat().st_size)
                    if current != signature:
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
                if x and ff.poll() is None:
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
    return bool(seen)
