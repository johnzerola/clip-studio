"""Create optional thumbnail and reframed copies of a registered video."""
import base64
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from engine import FF, command, encoder, probe
from workspace_data import register_exports


def best_thumbnail_time(path, duration):
    import cv2

    small = cv2.VideoCapture(str(path))
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    winner = (float("-inf"), duration * .25)
    try:
        for fraction in (.10, .24, .38, .52, .68, .84):
            at = duration * fraction
            small.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
            ok, frame = small.read()
            if not ok:
                continue
            scaled = cv2.resize(frame, (240, 426), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
            faces = face.detectMultiScale(gray, 1.15, 4, minSize=(25, 25))
            detail = min(180, math.sqrt(cv2.Laplacian(gray, cv2.CV_64F).var()) * 6)
            if len(faces):
                x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
                region = gray[y:y+h, x:x+w]
                detail += 65 + min(55, math.sqrt(cv2.Laplacian(region, cv2.CV_64F).var()) * 2)
            score = detail - abs(gray.mean() - 118) * .6
            winner = max(winner, (score, at))
    finally:
        small.release()
    return winner[1]


def suggest_thumbnail(path, title, at=None):
    from creative_studio import thumbnail

    duration, _ = probe(path, timeout=10)
    at = best_thumbnail_time(path, duration) if at is None else float(at)
    if not 0 <= at < duration:
        raise ValueError("Escolha um segundo dentro do clipe.")
    with TemporaryDirectory(prefix="codex-thumb-") as scratch:
        target = Path(scratch) / "thumb.jpg"
        thumbnail(path, target, " ".join(title.split())[:95], at)
        return {"at": round(at, 2), "jpeg": base64.b64encode(target.read_bytes()).decode("ascii")}


def reframe_copy(folder, path, *, zoom, x, y):
    zoom, x, y = (float(v) for v in (zoom, x, y))
    if not (1 < zoom <= 1.25 and 0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("Enquadramento fora dos limites.")
    duration, _, (width, height) = probe(path, timeout=15, include_size=True)
    w, h = round(width / zoom / 2) * 2, round(height / zoom / 2) * 2
    left, top = round((width - w) * x / 2) * 2, round((height - h) * y / 2) * 2
    graph = f"crop={w}:{h}:{left}:{top},scale={width}:{height}:flags=lanczos,setsar=1"
    target = path.with_name(f"{path.stem}-quadro-{uuid4().hex[:6]}.mp4")
    with TemporaryDirectory(prefix=".quadro-", dir=path.parent) as scratch:
        pending = Path(scratch) / "video.mp4"
        command([*FF, "-threads", "2", "-i", str(path), "-vf", graph, "-map", "0:v:0",
                 "-map", "0:a?", *encoder(quality=22), "-c:a", "copy", "-movflags", "+faststart", "-y", str(pending)],
                timeout=max(45, duration * 8))
        probe(pending, timeout=10)
        pending.replace(target)
    register_exports(folder, (target,))
    return target
