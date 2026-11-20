"""Verifica novas versões publicadas no GitHub sem interromper o painel."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

VERSION = "0.4.1"
OWNER = "johnzerola"
REPOSITORY = "clip-studio"
API_URL = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/releases/latest"
STATE_FILE = Path(__file__).resolve().parent / "update_check.local.json"


def _version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.strip().lstrip("vV").split("."))


def check_for_update(callback, *, force: bool = False) -> None:
    """Busca a release mais recente em background e entrega (tag, URL) se nova."""
    def worker():
        try:
            previous = {}
            if STATE_FILE.exists():
                previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            today = date.today().isoformat()
            if not force and previous.get("checked") == today:
                return

            request = urllib.request.Request(
                API_URL,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "Clip-Studio-Updater"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                release = json.loads(response.read().decode("utf-8"))
            tag = str(release.get("tag_name", "")).strip()
            url = str(release.get("html_url", "")).strip()
            STATE_FILE.write_text(json.dumps({"checked": today}, ensure_ascii=False), encoding="utf-8")
            if tag and url and _version(tag) > _version(VERSION):
                callback(tag, url)
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            # O painel permanece disponível sem rede ou quando a API está limitada.
            return

    threading.Thread(target=worker, name="clip-studio-update-check", daemon=True).start()
