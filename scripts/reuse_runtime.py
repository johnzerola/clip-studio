"""Reuse identical components across side-by-side Windows installations."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import venv


def versioned_siblings(root):
    for parent in sorted(root.parent.iterdir(), key=lambda path: path.name, reverse=True):
        if parent == root or not re.fullmatch(r"Clip-Studio-v\d+\.\d+\.\d+-\d+|Codex Video \d+\.\d+\.\d+", parent.name):
            continue
        if parent.resolve() == parent and (parent / "VERSION").is_file() and (parent / "scripts/check.py").is_file():
            yield parent


def hardlink_tree(source, target):
    if source.is_symlink() or source.is_junction():
        raise OSError("Vínculo encontrado no ambiente de origem")
    for directory, folders, files in source.walk():
        folders[:] = [name for name in folders if name != "__pycache__"]
        for name in folders:
            path = directory / name
            if path.is_symlink() or path.is_junction():
                raise OSError("Vínculo encontrado no ambiente de origem")
        destination = target / directory.relative_to(source)
        destination.mkdir(exist_ok=True, parents=True)
        for name in files:
            path = directory / name
            if not path.is_file() or path.is_symlink():
                raise OSError("Arquivo inválido no ambiente de origem")
            os.link(path, destination / name)


def share_node(root):
    relative = Path("desktop/runtime/node.exe")
    target = root / relative
    if not target.is_file() or target.resolve() != target:
        return False
    try:
        size = target.stat().st_size
        with target.open("rb") as stream:
            expected = hashlib.file_digest(stream, "sha256").digest()
    except OSError:
        return False
    for sibling in versioned_siblings(root):
        source = sibling / relative
        try:
            if not source.is_file() or source.resolve() != source or source.stat().st_size != size or source.samefile(target):
                continue
            with source.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").digest() != expected:
                    continue
            with TemporaryDirectory(prefix=".node-", dir=target.parent) as directory:
                temporary = Path(directory) / "node.exe"
                os.link(source, temporary)
                temporary.replace(target)
            return True
        except OSError:
            continue
    return False


def reuse(root):
    target = root / ".venv"
    requirements = (root / "requirements.txt").read_bytes()
    fingerprint = hashlib.sha256(requirements).hexdigest()
    if target.exists():
        return False
    relative_packages = Path("Lib/site-packages")
    for sibling in versioned_siblings(root):
        parent = sibling / ".venv"
        package_source = parent / relative_packages
        req = sibling / "requirements.txt"
        if not req.is_file() or req.read_bytes() != requirements or not package_source.is_dir() or package_source.is_junction():
            continue
        python = parent / "Scripts/python.exe"
        if not python.is_file():
            continue
        try:
            probe = subprocess.run([python, "-c", "import sys, struct; print(sys.version_info[:2], struct.calcsize('P'))"],
                                   capture_output=True, timeout=10)
            if probe.returncode or probe.stdout.strip() != b"(3, 13) 8":
                continue
            with TemporaryDirectory(prefix=".runtime-", dir=root) as directory:
                staging = Path(directory) / "venv"
                builder = venv.EnvBuilder(with_pip=False)
                builder.create(staging)
                hardlink_tree(package_source, staging / relative_packages)
                share = parent / "share"
                if share.is_dir():
                    hardlink_tree(share, staging / "share")
                staged_python = staging / "Scripts/python.exe"
                smoke = ("import cv2, faster_whisper, ffpyplayer.player, opentimelineio, streamlink, yt_dlp; "
                         "from pip._internal.cli.main import main; raise SystemExit(main(['check']))")
                result = subprocess.run([staged_python, "-c", smoke], capture_output=True, timeout=45)
                if result.returncode:
                    continue
                (staging / "reused-requirements.sha256").write_text(fingerprint, encoding="ascii")
                staging.rename(target)
                context = builder.ensure_directories(str(target))
                builder.create_configuration(context)
                builder.setup_scripts(context)
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve()
    if share_node(root):
        print("Runtime Node identico reaproveitado.")
    sys.exit(0 if reuse(root) else 1)
