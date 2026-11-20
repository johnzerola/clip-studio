"""Optional local Ollama setup with an explicit model download choice."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import urllib.request

import runtime_profile as runtime

MODELS = ("qwen3.5:4b", "qwen3.5:2b")


def installed_models():
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with client.open("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            return {item["name"] for item in json.load(response)["models"]}
    except (OSError, KeyError, ValueError, TypeError):
        return None


def recommended_model():
    available = installed_models() or set()
    return next((model for model in MODELS if model in available), MODELS[0])


def official_executable():
    found = shutil.which("ollama.exe")
    default = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
    return found or (str(default) if default.is_file() else None)


def install_model(model, notify):
    if model not in MODELS:
        raise ValueError("Escolha um dos modelos recomendados.")
    if model in (installed_models() or set()):
        return
    if not official_executable() and installed_models() is None:
        if os.name != "nt" or not (winget := shutil.which("winget.exe")):
            raise RuntimeError("Instale o Ollama em https://ollama.com/download.")
        notify("Instalando o Ollama pelo WinGet…")
        location = Path(os.environ["LOCALAPPDATA"]) / "Programs/Ollama"
        subprocess.run([winget, "install", "--exact", "--id", "Ollama.Ollama", "--source", "winget",
                        "--location", str(location), "--accept-source-agreements", "--accept-package-agreements"],
                       check=True, timeout=1800, **runtime.child_options(hide=True))
    executable = official_executable()
    if installed_models() is None and executable:
        subprocess.Popen([executable, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **runtime.child_options(hide=True))
        for _ in range(15):
            if installed_models() is not None:
                break
            time.sleep(1)
    if executable is None or installed_models() is None:
        raise RuntimeError("Abra o Ollama e volte a verificar a conexão.")
    notify(f"Baixando {model}. O tempo depende da conexão…")
    subprocess.run([executable, "pull", model], check=True, timeout=7200, **runtime.child_options(hide=True))
    if model not in (installed_models() or set()):
        raise RuntimeError("O modelo não apareceu na lista do Ollama.")


def show(parent=None, on_ready=None):
    import tkinter as tk
    from tkinter import messagebox, ttk

    window = tk.Toplevel(parent) if parent else tk.Tk()
    window.title("IA local do Clip Studio")
    window.geometry("560x285")
    body = ttk.Frame(window, padding=20)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Ollama para avaliar a fala e os quadros do corte", wraplength=490).pack(anchor="w")
    ttk.Label(body, text="4B é o recomendado. 2B usa menos memória. A edição e a nota local funcionam sem modelo.",
              wraplength=490).pack(anchor="w", pady=(6, 12))
    selection = tk.StringVar(value=MODELS[0])
    ttk.Combobox(body, textvariable=selection, values=MODELS, state="readonly", width=20).pack(anchor="w")
    status = tk.StringVar(value="Verificando instalação…")
    ttk.Label(body, textvariable=status, wraplength=490).pack(anchor="w", pady=12)
    messages = queue.Queue()
    active = False

    def refresh():
        models = installed_models()
        available = [model for model in MODELS if model in (models or set())]
        if available:
            messages.put(("selection", available[0]))
        messages.put(("status", "Modelos disponíveis: " + ", ".join(available) if available
                      else "Ollama sem modelo recomendado." if models is not None else "Ollama sem conexão."))

    def start():
        nonlocal active
        model = selection.get()
        if not messagebox.askyesno("Instalar IA opcional",
                                  f"Instalar o Ollama, se necessário, e baixar {model}?\n"
                                  "O runtime e o modelo podem ocupar vários GB.", parent=window):
            return
        active = True
        button.config(state="disabled")

        def job():
            try:
                install_model(model, lambda text: messages.put(("status", text)))
                messages.put(("ready", model))
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                messages.put(("error", str(error)))
        threading.Thread(target=job, daemon=True).start()

    def update():
        nonlocal active
        while not messages.empty():
            kind, value = messages.get_nowait()
            if kind == "selection":
                selection.set(value)
            elif kind == "status":
                status.set(value)
            else:
                active = False
                button.config(state="normal")
                if kind == "ready":
                    status.set(f"{value} pronto para revisão no Clip Studio.")
                    if on_ready:
                        on_ready(value)
                else:
                    status.set(f"Falha na configuração. {value}")
        window.after(200, update)

    def close():
        if not active:
            window.destroy()

    button = ttk.Button(body, text="Instalar ou ativar modelo…", command=start)
    button.pack(anchor="w")
    window.protocol("WM_DELETE_WINDOW", close)
    window.after(200, update)
    threading.Thread(target=refresh, daemon=True).start()
    if not parent:
        window.mainloop()


if __name__ == "__main__":
    show()
