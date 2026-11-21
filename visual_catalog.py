"""Local preferences and personal media shared by the desktop and V9 workers."""
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from broll_library import Asset, MEDIA, STILLS, director_items


@contextmanager
def connect():
    directory = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Codex Video"
    directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / "visual-library.sqlite3", timeout=8)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS visual_selection (id TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS visual_personal (id TEXT PRIMARY KEY, path TEXT NOT NULL,
                   label TEXT NOT NULL, role TEXT NOT NULL, cues TEXT NOT NULL, source TEXT NOT NULL,
                   license TEXT NOT NULL)""")
        yield db


def catalog(root):
    with connect() as db:
        assets = director_items(root / "biblioteca/Acervo", group="Acervo incluído")
        defaults = {asset.digest for asset in assets}
        for key, path, label, role, cues, source, license in db.execute("SELECT * FROM visual_personal ORDER BY rowid DESC"):
            if key not in defaults:
                assets.append(Asset(f"Minha biblioteca/{label}", Path(path), "Minha biblioteca", label, tuple(json.loads(cues)), role,
                                    key, "authorized", license, source))
        settings = dict(db.execute("SELECT id,enabled FROM visual_selection"))
    return [(asset, bool(settings.get(asset.digest, asset.digest in defaults)), asset.digest not in defaults) for asset in assets]


def item_for(root, key):
    match = next((row for row in catalog(root) if row[0].digest == key), None)
    if not match:
        raise ValueError("Mídia fora da biblioteca cadastrada.")
    return match


def import_asset(data):
    source = Path(data.get("path") or "").resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in MEDIA or not data.get("authorized"):
        raise ValueError("Selecione uma mídia real e confirme que você pode usá-la.")
    label, license = str(data.get("label") or source.stem).strip()[:120], str(data.get("license") or "").strip()[:180]
    credit = str(data.get("source") or "Arquivo próprio").strip()[:480]
    role = data.get("role")
    cues = list(dict.fromkeys(part.strip() for part in str(data.get("cues") or "").split(",") if part.strip()))
    if role not in ("meme", "broll", "background") or not label or not license or (role != "background" and not cues):
        raise ValueError("Informe o tipo, a licença e as frases para ativar a mídia.")
    if len(cues) > 12 or any(len(cue) > 70 for cue in cues):
        raise ValueError("Use até 12 frases de até 70 caracteres.")
    with source.open("rb") as stream:
        key = hashlib.file_digest(stream, "sha256").hexdigest()
    with connect() as db:
        db.execute("""INSERT INTO visual_personal VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                   path=excluded.path,label=excluded.label,role=excluded.role,cues=excluded.cues,
                   source=excluded.source,license=excluded.license""",
                   (key, str(source), label, role, json.dumps(cues, ensure_ascii=False), credit, license))
    return key


def activate(root, key, enabled):
    item_for(root, key)
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO visual_selection VALUES (?,?)", (key, int(bool(enabled))))


def card(asset, enabled, personal):
    possibly_link = asset.attribution.rsplit(" · ", 1)[-1]
    url = urlsplit(possibly_link)
    return {"id": asset.digest, "label": asset.label, "role": asset.role, "cues": asset.cues, "license": asset.license,
            "source": asset.attribution, "sourceUrl": possibly_link if url.scheme in ("http", "https") and url.netloc else "",
            "enabled": enabled, "personal": personal, "available": asset.path.is_file(),
            "kind": "image" if asset.path.suffix.lower() in STILLS | {".gif"} else "video"}
