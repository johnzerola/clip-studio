"""Finishing decisions shared by the panel and CLI."""
import math
import random
import wave
from array import array
from pathlib import Path
from editorial import normalized


def caption_groups(words):
    group = []
    for start, end, word in sorted(set(words)):
        if end <= start or not word.strip():
            continue
        if group and (start - group[-1][1] > .48 or len(group) >= 4
                      or len(" ".join([*(p[2] for p in group), word])) > 28):
            yield group
            group = []
        group.append((start, end, word))
        if word.endswith((".", "?", "!")) and len(group) > 1:
            yield group
            group = []
    if group:
        yield group


def accent_shots(shots):
    selected, previous = {}, -12.0
    elapsed = 0.0
    for index, (start, end, style) in enumerate(shots):
        if (index and elapsed >= 3 and elapsed - previous >= 12 and end - start >= .85
                and style != shots[index - 1][2] and style in {"face", "game", "gamecam"}
                and len(selected) < 3):
            selected[index] = elapsed
            previous = elapsed
        elapsed += end - start
    return selected


def mix_cues(path, duration, timings):
    rate = 24000
    audio = array("h", [0]) * math.ceil((duration + .15) * rate)
    rng = random.Random(42)
    for time in timings:
        begin = round(time * rate)
        for i in range(round(.21 * rate)):
            t = i / rate
            attack = min(1, t / .027) * math.exp(-t * 18)
            signal = .72 * math.sin(2 * math.pi * (145 * t + 630 * t * t)) + .28 * rng.uniform(-1, 1)
            if begin + i < len(audio):
                audio[begin + i] = round(2200 * attack * signal)
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(audio.tobytes())


def pick_broll(folder, shots, words):
    if not folder:
        return {}
    assets = {}
    for path in sorted(Path(folder).iterdir()):
        cue = normalized(path.stem)
        if path.is_file() and len(cue) >= 4 and path.suffix.lower() in {".mp4", ".mov", ".webm", ".png", ".jpg"}:
            assets.setdefault(cue, path.resolve())
    for i, (start, end, style) in enumerate(shots):
        if style not in {"split", "gamecam", "game"}:
            continue
        for time, _, word in words:
            if start + .5 <= time <= end - 1.3 and normalized(word) in assets:
                return {i: (assets[normalized(word)], time - start)}
    return {}
