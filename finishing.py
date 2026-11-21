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
    candidates = []
    elapsed = 0.0
    for index, (start, end, style) in enumerate(shots):
        if (index and elapsed >= 3 and end - start >= .85 and style != shots[index - 1][2]
                and style in {"face", "game", "gamecam"}):
            candidates.append((style != "face", elapsed, index))
        elapsed += end - start
    selected = {}
    for _, position, index in sorted(candidates):
        if all(abs(position - prior) >= 12 for prior in selected.values()):
            selected[index] = position
            if len(selected) == 3:
                break
    return dict(sorted(selected.items()))


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


def audio_runs(shots, frame_counts, fps=30):
    runs = []
    for (start, end, _), frames in zip(shots, frame_counts):
        if runs and abs(runs[-1][1] - start) <= .015:
            a, _, previous = runs.pop()
            runs.append((a, end, previous + frames))
        else:
            runs.append((start, end, frames))
    return [(a, b, frames / fps) for a, b, frames in runs]


def pick_broll(folder, shots, words, *, full_screen=False, selected=(), reaction=False):
    from broll_library import MEDIA

    assets = {}
    for path in sorted(Path(folder).iterdir()) if folder else ():
        wide = full_screen and path.stem.casefold().startswith("tela-")
        cue = normalized(path.stem[5:] if wide else path.stem)
        if path.is_file() and len(cue) >= 4 and path.suffix.lower() in MEDIA:
            assets.setdefault(cue, path.resolve())
    for path, cues in selected:
        if path.is_file():
            for cue in cues:
                key = tuple(filter(None, (normalized(word) for word in cue.split())))
                if key:
                    assets.setdefault(key, path)
    if not assets:
        return {}
    sizes = sorted({len(cue) for cue in assets if isinstance(cue, tuple)}, reverse=True)
    for i, (start, end, style) in enumerate(shots):
        if style not in {"split", "gamecam", "game"} and not (reaction and style in {"face", "reaction"}):
            continue
        spoken = [(time, normalized(word)) for time, finish, word in words
                  if time >= start and finish <= end and normalized(word)]
        for index, (time, word) in enumerate(spoken):
            if not start + .5 <= time <= end - 1.3:
                continue
            for size in sizes:
                phrase = spoken[index:index + size]
                if len(phrase) != size or phrase[-1][0] - time > size * .65:
                    continue
                asset = assets.get(tuple(token for _, token in phrase))
                if asset:
                    return {i: (asset, time - start)}
            if word in assets:
                return {i: (assets[word], time - start)}
    return {}
