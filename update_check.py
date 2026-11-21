"""Descoberta pública de releases, com cache de 20 minutos e entrega por fila."""
import json
import re
import threading
import time
import urllib.request
from pathlib import Path

VERSION = "0.7.7"
CHECK_INTERVAL_SECONDS = 20 * 60
REPO = "johnzerola/clip-studio"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
STATE_FILE = Path(__file__).resolve().parent / "update_check.local.json"
_LOCK = threading.Lock()


def _version(value):
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Versão incompatível")
    return tuple(map(int, value.lstrip("v").split(".")))


def check_for_update(callback, *, force=False):
    def worker():
        if not _LOCK.acquire(blocking=False):
            return
        try:
            cached = {}
            try:
                cached = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            release = cached.get("release")
            checked = cached.get("checked_at", 0)
            if force or not isinstance(release, dict) or not isinstance(checked, (int, float)) or time.time() - checked >= CHECK_INTERVAL_SECONDS:
                request = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "Clip-Studio"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    release = json.load(response)
                if not isinstance(release, dict):
                    return
                try:
                    STATE_FILE.write_text(json.dumps({"checked_at": time.time(), "release": release}), encoding="utf-8")
                except OSError:
                    pass
            if not release.get("draft") and not release.get("prerelease") and _version(str(release.get("tag_name", ""))) > _version(VERSION):
                callback(release)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        finally:
            _LOCK.release()
    task = threading.Thread(target=worker, daemon=True, name="update-check")
    task.start()
    return task
