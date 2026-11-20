"""Instala uma release em pasta irmã; a instalação anterior permanece recuperável."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

REPO = "johnzerola/clip-studio"
MAX_BYTES = 100 * 1024 * 1024


def asset_url(url, tag, name):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment or parsed.path != f"/{REPO}/releases/download/{tag}/{name}":
        raise ValueError("Endereço da atualização inválido.")
    return url


def select_assets(release):
    tag = str(release.get("tag_name", ""))
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Versão não suportada.")
    assets = {a.get("name"): a for a in release.get("assets", []) if isinstance(a, dict)}
    urls = []
    for name in ("Clip-Studio-Windows.zip", "Clip-Studio-Windows.zip.sha256"):
        item = assets.get(name)
        if not item:
            raise ValueError("Esta release ainda não tem pacote e checksum. Tente mais tarde.")
        urls.append(asset_url(item.get("browser_download_url", ""), tag, name))
    return tag, urls


def download(url, target, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "Clip-Studio-Updater"})
    total = 0
    with urllib.request.urlopen(request, timeout=30) as response, Path(target).open("xb") as output:
        while chunk := response.read(256 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError("Pacote excede o limite de tamanho.")
            output.write(chunk)


def extract_package(archive, expected, destination):
    with Path(archive).open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected) or actual != expected.lower():
        raise ValueError("Checksum da atualização não confere.")
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_BYTES:
            raise ValueError("Pacote expandido excede o limite.")
        for entry in entries:
            name = entry.filename
            parts = PurePosixPath(name).parts
            if (not parts or parts[0] != "Clip-Studio" or ".." in parts or "\\" in name or ":" in name
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Caminho inesperado no ZIP.")
            relative = Path(*parts[1:])
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Caminho fora da atualização.")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 256 * 1024)
    for required in ("painel.py", "scripts/install.ps1", "Iniciar.cmd", "VERSION"):
        if not (destination / required).is_file():
            raise ValueError("Pacote incompleto.")


def start_update(root, release):
    tag, _ = select_assets(release)
    scratch = Path(tempfile.mkdtemp(prefix="clip-update-"))
    helper = scratch / "update_install.py"
    shutil.copyfile(Path(__file__), helper)
    request = scratch / "request.json"
    request.write_text(json.dumps({"root": str(Path(root).resolve()), "release": release}), encoding="utf-8")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen([sys.executable, "-X", "utf8", str(helper), str(request)],
                     cwd=scratch, creationflags=flags, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return tag


def install(request, notify):
    root = Path(request["root"]).resolve(strict=True)
    tag, urls = select_assets(request["release"])
    # Pasta única: nunca substitui outra instalação ou uma atualização anterior.
    destination = root.parent / ("Clip-Studio-" + tag + "-" + str(time.time_ns()))
    scratch = Path(tempfile.mkdtemp(prefix="clip-package-"))
    log = scratch / "installation.log"
    notify("Baixando a atualização…")
    package, checksum = scratch / "package.zip", scratch / "checksum.txt"
    download(urls[0], package, MAX_BYTES)
    download(urls[1], checksum, 4096)
    expected = checksum.read_text(encoding="utf-8-sig").split()[0]
    notify("Verificando e preparando a nova instalação…")
    extract_package(package, expected, destination)
    if (destination / "VERSION").read_text(encoding="utf-8").strip() != tag[1:]:
        raise ValueError("A versão do pacote diverge da release.")
    prefs = root / "preferencias.local.json"
    if prefs.is_file():
        settings = json.loads(prefs.read_text(encoding="utf-8"))
        settings["output_dir"] = str(Path(settings.get("output_dir") or root / "resultados").resolve())
        (destination / prefs.name).write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    else:
        (destination / "preferencias.local.json").write_text(json.dumps({"output_dir": str(root / "resultados")}), encoding="utf-8")
    # Mantém a conta OAuth protegida pelo Windows e o histórico da fila.
    account = root / "work/youtube-account.dpapi"
    if account.is_file():
        (destination / "work").mkdir(exist_ok=True)
        shutil.copy2(account, destination / "work" / account.name)
    database = root / "work/jobs.sqlite3"
    if database.is_file():
        import sqlite3
        (destination / "work").mkdir(exist_ok=True)
        with sqlite3.connect(database) as old, sqlite3.connect(destination / "work/jobs.sqlite3") as new:
            old.backup(new)
    notify("Instalando as bibliotecas. Isso pode demorar alguns minutos…")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "RemoteSigned", "-File",
            str(destination / "scripts/install.ps1"), "-SkipShortcut"], cwd=destination,
            stdout=output, stderr=subprocess.STDOUT, creationflags=flags)
    if result.returncode:
        raise RuntimeError("Instalação não concluída. Sua versão anterior permanece disponível. Registro: " + str(log))
    # Atalho só muda depois que a nova instalação passou no diagnóstico.
    shortcut_script = scratch / "shortcut.ps1"
    shortcut_script.write_text("""param([string]$Project)
$ErrorActionPreference='Stop'
$w=New-Object -ComObject WScript.Shell
$s=$w.CreateShortcut((Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Clip Studio.lnk'))
$s.TargetPath=Join-Path $Project 'Iniciar.cmd'
$s.WorkingDirectory=$Project
$s.Save()
""", encoding="utf-8-sig")
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "RemoteSigned", "-File", str(shortcut_script), str(destination)], creationflags=flags, check=True)
    notify("Atualização concluída. Abrindo o Clip Studio…")
    os.startfile(destination / "Iniciar.cmd")
    return destination


def main():
    import queue
    import threading
    import tkinter as tk
    from tkinter import messagebox, ttk
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    window = tk.Tk()
    window.title("Atualização do Clip Studio")
    window.geometry("510x160")
    status = tk.StringVar(value="Preparando a atualização…")
    ttk.Label(window, textvariable=status, wraplength=470, padding=20).pack(fill="both", expand=True)
    ttk.Label(window, text="Sua instalação anterior será preservada.", padding=10).pack()
    messages = queue.Queue()
    window.protocol("WM_DELETE_WINDOW", lambda: None)
    def work():
        try:
            install(request, lambda message: messages.put(("status", message)))
            messages.put(("done", ""))
        except Exception as error:
            messages.put(("error", str(error)))
    def poll():
        while not messages.empty():
            kind, text = messages.get_nowait()
            if kind == "status":
                status.set(text)
            else:
                if kind == "error":
                    messagebox.showerror("Atualização não concluída", text + "\nAbra a instalação anterior para continuar.", parent=window)
                window.destroy()
                return
        window.after(150, poll)
    threading.Thread(target=work, daemon=True).start()
    window.after(150, poll)
    window.mainloop()


if __name__ == "__main__":
    main()
