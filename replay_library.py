"""Public replay discovery and persistent per-destination import history."""
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

@dataclass(frozen=True)
class Replay:
    platform: str
    id: str
    url: str


def archive_url(url):
    p = urlsplit(url)
    path = p.path.strip("/")
    if p.hostname == "www.twitch.tv" and "/" not in path:
        return "twitch", f"https://www.twitch.tv/{path}/videos?filter=archives"
    if p.hostname == "kick.com" and "/" not in path:
        return "kick", f"https://kick.com/{path}/videos"
    if p.hostname == "www.youtube.com" and (path.startswith("@") or path.startswith("channel/")):
        return "youtube", f"https://www.youtube.com/{path.removesuffix('/live')}/streams"
    raise ValueError("Para buscar replays, use o link de um canal da Twitch, Kick ou YouTube.")


def list_replays(python, url, count):
    from engine import command
    platform, archive = archive_url(url)
    raw = command([python, "-m", "yt_dlp", "--ignore-config", "--compat-options", "no-certifi",
                   "--socket-timeout", "10", "--extractor-retries", "1", "--flat-playlist",
                   "--playlist-end", str(max(12, count * 4)), "--dump-single-json", "--", archive], timeout=50)
    result = {}
    for row in json.loads(raw).get("entries", ()):
        if not row or row.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
            continue
        key = str(row.get("id", ""))
        if platform == "youtube":
            if row.get("live_status") != "was_live" or not re.fullmatch(r"[\w-]{11}", key, re.ASCII):
                continue
            target = f"https://www.youtube.com/watch?v={key}"
        elif platform == "twitch":
            key = key.removeprefix("v")
            if not key.isascii() or not key.isdecimal():
                continue
            target = f"https://www.twitch.tv/videos/{key}"
        else:
            if not re.fullmatch(r"[0-9a-f-]{36}", key) or not row.get("duration"):
                continue
            target = f"https://kick.com/{urlsplit(url).path.strip('/')}/videos/{key}"
        result.setdefault(key, Replay(platform, key, target))
        if len(result) == count:
            break
    return list(result.values())


def claim(database, replay):
    with sqlite3.connect(database, timeout=20) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS replays (
                    platform TEXT, id TEXT, status TEXT, changed REAL, PRIMARY KEY(platform,id))""")
        now = time.time()
        return bool(db.execute("""INSERT INTO replays VALUES (?, ?, 'working', ?)
            ON CONFLICT(platform,id) DO UPDATE SET status='working', changed=excluded.changed
            WHERE replays.status='retry' OR (replays.status='working' AND replays.changed < ?)""",
            (replay.platform, replay.id, now, now - 12*3600)).rowcount)


def finish(database, replay, ok):
    with sqlite3.connect(database, timeout=20) as db:
        db.execute("UPDATE replays SET status=?,changed=? WHERE platform=? AND id=?",
                   ("done" if ok else "retry", time.time(), replay.platform, replay.id))
