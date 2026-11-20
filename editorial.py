"""Conservative transcript edits and exact source ranges for the render engine."""
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Cleanup:
    silence: bool = False
    repeats: bool = False
    fillers: bool = False
    speech: bool = False
    pause: float = 0.9
    noise: int = -36
    padding: float = 0.16
    speech_gaps: bool = False


def normalized(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in text if char.isalnum())


def silence_edits(log, low, high, padding):
    start = None
    for match in re.finditer(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)", log):
        value = max(0, float(match[2])) + low
        if match[1] == "start":
            start = value
        elif start is not None:
            a = start if start <= low + .02 else start + padding
            b = high if value >= high - .02 else value - padding
            if b - a >= .18:
                yield a, b, "silêncio", ""
            start = None
    if start is not None and high - start - padding >= .18:
        yield start + padding, high, "silêncio", ""


def transcript_edits(words, settings):
    tokens = [normalized(text) for _, _, text in words]
    i = 0
    while i < len(words):
        a, b, text = words[i]
        size = 0
        if settings.repeats:
            for n in range(min(5, (len(words) - i) // 2), 0, -1):
                gap = words[i + n][0] - words[i + n - 1][1]
                original = tokens[i:i + n]
                if (all(original) and 0 <= gap <= .85 and original == tokens[i + n:i + 2 * n]
                        and (n > 1 or not text.endswith(("!", "?", ".")))):
                    size = n
                    break
        if size:
            # Keep the most recent take. Leave a small margin around adjacent phonemes.
            end = words[i + size][0]
            start = max(a - .04, words[i - 1][1] + .025) if i else a
            if end - .025 - start >= .11:
                yield start, end - .025, "repetição", " ".join(w[2] for w in words[i:i + size])
            i += size
            continue
        if settings.fillers and tokens[i] in {"ah", "ahn", "aam", "uh", "uhm", "hmm", "erm", "ham"}:
            prior_gap = a - words[i - 1][1] if i else 1
            next_gap = words[i + 1][0] - b if i + 1 < len(words) else 1
            if min(prior_gap, next_gap) >= .075 and b - a >= .11:
                yield a - .025, b + .025, "hesitação", text
        i += 1


def speech_gap_edits(words, cleanup):
    threshold = max(2.4, cleanup.pause * 2.5)
    if len(words) < 6:
        return
    for prior, following in zip(words, words[1:]):
        if following[0] - prior[1] >= threshold:
            yield prior[1] + .35, following[0] - .35, "pausa na fala", ""


def clean_ranges(low, high, edits, words):
    """Keep detected speech at silence edges and ignore edits that erase a whole segment."""
    removal = []
    for a, b, reason, text in edits:
        a, b = max(low, a), min(high, b)
        if reason == "silêncio":
            overlaps = [(start, end) for start, end, _ in words if start < b and end > a]
            cursor = a
            for start, end in overlaps:
                if min(b, start - .08) - cursor >= .2:
                    removal.append((cursor, min(b, start - .08), reason, text))
                cursor = max(cursor, end + .08)
            a = cursor
        if b - a >= .10:
            removal.append((a, b, reason, text))
    cursor = low
    kept = []
    removal.sort()
    for a, b, _, _ in removal:
        if a > cursor + .06:
            kept.append((cursor, a))
        cursor = max(cursor, b)
    if high > cursor + .06:
        kept.append((cursor, high))
    if sum(b - a for a, b in kept) < min(.6, (high - low) * .35):
        return [(low, high)], []
    return kept, [dict(start=a, end=b, reason=r, text=t) for a, b, r, t in removal]


def refine_montage(parts, words, total):
    """Prefer intact phrases and shared vocabulary near the already-ranked highlights."""
    boundaries = []
    for prior, following in zip(words, words[1:]):
        gap = following[0] - prior[1]
        if gap >= .24 or (gap >= .06 and prior[2].endswith((".", "!", "?"))):
            boundaries.append((prior[1] + following[0]) / 2)
    result, previous_terms = [], set()
    for i, (start, end) in enumerate(parts):
        lower = max(result[-1][1] if result else 0, start - 3)
        upper = min(parts[i + 1][0] if i + 1 < len(parts) else total, end + 3)
        starts = [(start, False), *((p, True) for p in boundaries if lower <= p <= start + 3)]
        ends = [(end, False), *((p, True) for p in boundaries if end - 3 <= p <= upper)]
        best, best_terms, best_score = (start, end), set(), -float("inf")
        for a, start_boundary in starts:
            for b, end_boundary in ends:
                if b - a < max(.5, (end - start) * .8):
                    continue
                spoken = [normalized(text) for s, e, text in words if s >= a and e <= b]
                terms = {t for t in spoken if len(t) >= 5}
                value = (1.3 * (start_boundary + end_boundary) + .55 * min(5, len(terms & previous_terms))
                         + .07 * min(20, len(spoken)) - .34 * (abs(a - start) + abs(b - end)))
                if value > best_score:
                    best, best_terms, best_score = (a, b), terms, value
        result.append(best)
        previous_terms |= best_terms
    return result

def quiet_live_edits(low, high, bins, words, noise, step=2.):
    """Remove only long stretches with quiet audio, little motion and no speech."""
    gate = 32768 * 10 ** (noise / 20)
    live_motion = [motion for _, motion, _ in bins if motion >= 2]
    background = sorted(live_motion)[len(live_motion)//2] if live_motion else 0.
    motion_gate = min(2.5, max(.85, background * .28))
    idle = None
    for index in range(len(bins) + 1):
        start = low + index * step
        if index < len(bins):
            rms, movement, face_motion = bins[index]
            if (rms < gate and movement < motion_gate and face_motion < motion_gate
                    and not any(a < start + step and b > start for a, b, _ in words)):
                if idle is None:
                    idle = start
                continue
        if idle is not None:
            end = min(start, high)
            if end - idle >= 4:
                yield idle + .4, end - .4, "espera sem fala nem ação", ""
            idle = None
