"""On-demand sizes for Codex installations, caches and capture folders."""
from pathlib import Path
import os
import re
import shutil
import stat


def measured(paths):
    total = shared = 0
    seen = set()
    for root in paths:
        if not root.is_dir() or root.is_symlink() or root.is_junction():
            continue
        for directory, folders, files in root.walk():
            folders[:] = [name for name in folders if not (directory / name).is_junction()]
            for name in files:
                try:
                    found = (directory / name).lstat()
                except OSError:
                    continue
                key = found.st_dev, found.st_ino
                if not stat.S_ISREG(found.st_mode) or key in seen:
                    continue
                seen.add(key)
                total += found.st_size
                if found.st_nlink > 1:
                    shared += found.st_size
    return {"bytes": total, "shared": shared}


def storage(root, outputs):
    installs = [item for item in root.parent.iterdir() if item == root or (
        re.fullmatch(r"Clip-Studio-v\d+\.\d+\.\d+-\d+|Codex Video \d+\.\d+\.\d+", item.name)
        and (item / "VERSION").is_file())]
    capture_dirs = set()
    for output in set(outputs):
        if output.is_dir():
            capture_dirs.update(path / "Capturas" for path in output.iterdir()
                                if path.is_dir() and re.fullmatch(r"\d{8}_\d{6}_[a-f0-9]{6}", path.name))
    local = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Codex Video"
    profile = local / "Panel/Default"
    home = Path.home()
    hf = Path(os.getenv("HF_HOME") or home / ".cache/huggingface")
    caches = [profile / "Cache", profile / "Code Cache", profile / "GPUCache", hf / "hub"]
    return {"versions": [{"label": (item / "VERSION").read_text(encoding="utf-8").strip(), "name": item.name,
                          "active": item == root, **measured([item])} for item in sorted(installs)],
            "cache": measured(caches), "captures": measured(capture_dirs),
            "free": shutil.disk_usage(root).free}
