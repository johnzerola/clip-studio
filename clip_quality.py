"""Small local signatures and retention-based ranking for the posting queue."""
import hashlib
import json
import math
import subprocess
from pathlib import Path

from runtime_profile import child_options

MIN_VIEWS = 100


def transcript_signature(words):
    if len(words) < 14:
        return []
    return sorted({hashlib.blake2b(" ".join(words[i:i + 3]).encode(), digest_size=8).hexdigest()
                   for i in range(len(words) - 2)})


def media_signature(path, duration):
    """Sample three 72-byte grayscale images without transcoding or saving a proxy."""
    if not duration or duration < 2:
        return []
    signature = []
    for point in (.2, .5, .8):
        try:
            pixels = subprocess.run(
                ["ffmpeg", "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
                 "-ss", str(duration * point), "-i", str(path), "-an", "-frames:v", "1",
                 "-vf", "scale=9:8,format=gray", "-c:v", "rawvideo", "-threads", "1",
                 "-f", "rawvideo", "pipe:1"], capture_output=True, check=True, timeout=5,
                **child_options(force_low=True, hide=True)).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        if len(pixels) != 72 or max(pixels) - min(pixels) < 24:
            return []
        difference = [pixels[n] > pixels[n + 1] for n in range(72) if n % 9 != 8]
        signature.append(sum(1 << i for i, bit in enumerate(difference) if bit))
    return signature if (signature[0] ^ signature[2]).bit_count() >= 8 else []


def register_similarity(db, key, words, duration, visual, source="", ranges=()):
    candidates = db.execute("""SELECT s.*, c.path FROM clip_signatures s JOIN clips c ON c.id=s.clip
                            WHERE c.result='ready' AND c.id<>?
                            ORDER BY c.updated DESC LIMIT 250""", (key,))
    transcript = transcript_signature(words)
    similar = None
    for row in candidates:
        if not row["path"] or not Path(row["path"]).is_file():
            continue
        older_ranges = json.loads(row["ranges"])
        if source and source == row["source"] and ranges and older_ranges:
            shared = sum(max(0., min(b, d) - max(a, c)) for a, b in ranges for c, d in older_ranges)
            if shared >= .8 * max(sum(b-a for a,b in ranges), sum(d-c for c,d in older_ranges)):
                similar = row["duplicate_of"] or row["clip"]
                break
        prior = set(json.loads(row["speech"]))
        if prior and transcript:
            overlap = len(prior.intersection(transcript))
            if overlap >= 10 and overlap / (len(prior) + len(transcript) - overlap) >= .66:
                similar = row["duplicate_of"] or row["clip"]
                break
        previous_visual = json.loads(row["visual"])
        if visual and previous_visual and abs(duration - row["duration"]) <= max(.3, duration * .08):
            distances = [(a ^ b).bit_count() for a, b in zip(visual, previous_visual)]
            if max(distances) <= 6 and sum(distances) <= 12:
                similar = row["duplicate_of"] or row["clip"]
                break
    db.execute("INSERT OR IGNORE INTO clip_signatures VALUES (?,?,?,?,?,?,?)",
               (key, json.dumps(transcript), json.dumps(visual), duration,
                source, json.dumps(ranges), similar))


def retention_adjustments(db, platform):
    rows = list(db.execute("""SELECT c.score, r.retention FROM clip_retention r JOIN clips c ON c.id=r.clip
                            WHERE r.platform=? AND r.views>=? AND c.result='ready'
                            ORDER BY r.updated DESC LIMIT 300""", (platform, MIN_VIEWS)))
    if len(rows) < 5:
        return {}, len(rows)
    data = [(row["score"] // 10, min(150., row["retention"])) for row in rows]
    baseline = sum(value for _, value in data) / len(data)
    buckets = {}
    for bucket, value in data:
        buckets.setdefault(bucket, []).append(value)
    adjustments = {bucket: max(-8, min(8, round((sum(values) / len(values) - baseline) / 4
                                                  * len(values) / (len(values) + 3))))
                   for bucket, values in buckets.items() if len(values) >= 3}
    return adjustments, len(rows)


def retention_values(db, clip, platform, value=None, views=None):
    if value is not None:
        if not math.isfinite(value) or not 0 <= value <= 1000 or views is None or not 0 <= views <= 2**53:
            raise ValueError("Informe uma porcentagem de 0 a 1000 e visualizações válidas.")
        if not db.execute("SELECT 1 FROM clips WHERE result='ready' AND id=?", (clip,)).fetchone():
            raise ValueError("Escolha um clipe aprovado para registrar retenção.")
        db.execute("""INSERT INTO clip_retention (clip,platform,retention,views) VALUES (?,?,?,?)
                      ON CONFLICT(clip,platform) DO UPDATE SET retention=excluded.retention,
                      views=excluded.views, updated=CURRENT_TIMESTAMP""", (clip, platform, value, views))
    row = db.execute("SELECT retention, views FROM clip_retention WHERE clip=? AND platform=?",
                     (clip, platform)).fetchone()
    return tuple(row) if row else (None, None)
