"""Fetch an optional, checksummed media kit during a Codex installation."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
from zipfile import BadZipFile

from gta_kit import ROOT, installed_archive, validate_archive
from update_install import REPO, asset_url, download

NAME = "Codex-Kit-GTA6.zip"
MAX_KIT_BYTES = 200_000_000


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def install_kit(fetch=download):
    manifest = ROOT / "biblioteca/kit-gta6-release.json"
    if not manifest.is_file():
        return "Kit GTA 6 incluído para uso com gameplay próprio."

    expected = json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
    version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
    if not isinstance(expected, str) or not re.fullmatch("[a-f0-9]{64}", expected):
        raise ValueError("Checksum do kit inválido.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Versão do kit inválida.")
    tag = f"v{version}"
    url = asset_url(f"https://github.com/{REPO}/releases/download/{tag}/{NAME}", tag, NAME)
    destination = installed_archive()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and file_digest(destination) == expected:
        validate_archive(destination)
        return "Kit completo GTA 6 reaproveitado."

    with tempfile.TemporaryDirectory(prefix="gta6-", dir=destination.parent) as folder:
        incoming = Path(folder) / NAME
        fetch(url, incoming, MAX_KIT_BYTES)
        if incoming.stat().st_size > MAX_KIT_BYTES or file_digest(incoming) != expected:
            raise ValueError("Checksum do kit não confere.")
        validate_archive(incoming)
        incoming.replace(destination)
    return "Kit completo GTA 6 instalado."


if __name__ == "__main__":
    try:
        print(install_kit())
    except (BadZipFile, KeyError, OSError, TypeError, ValueError) as error:
        print(f"Kit GTA 6 adicional indisponível: {error}")
        raise SystemExit(1)
