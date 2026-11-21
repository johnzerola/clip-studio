"""On-demand trim preview. No proxy or decoded frame cache is written to disk."""
import json
import math
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from runtime_profile import child_options


def extract_frame(path, at):
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
         "-ss", f"{at:.3f}", "-i", str(path), "-an", "-frames:v", "1",
         "-vf", "scale=360:360:force_original_aspect_ratio=decrease", "-c:v", "ppm",
         "-f", "image2pipe", "pipe:1"],
        capture_output=True, check=True, timeout=10, **child_options(force_low=True, hide=True)).stdout


def open_trim(parent, source, ranges, on_apply, parse_time):
    from engine import probe

    window = tk.Toplevel(parent)
    window.title("Ajustar corte")
    window.geometry("718x560")
    window.minsize(660, 515)
    if parent.winfo_viewable():
        window.transient(parent)
    else:
        window.attributes("-topmost", True)
    body = ttk.Frame(window, padding=16)
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(1, weight=1)
    ttk.Label(body, text=source.name, font=("Segoe UI Semibold", 13)).grid(row=0, column=0, sticky="w")
    picture = tk.Label(body, text="Carregando vídeo…", bg="#102c34", fg="#ffffff")
    picture.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 6))
    drafts = list(ranges)
    active_index = 0
    segments = None
    if len(drafts) > 1:
        segments = ttk.Combobox(body, values=[f"Trecho {i + 1}" for i in range(len(drafts))],
                                state="disabled", width=14)
        segments.current(0)
        segments.grid(row=0, column=1, sticky="e")
    position = tk.DoubleVar()
    slider = ttk.Scale(body, from_=0, to=1, variable=position)
    slider.grid(row=2, column=0, columnspan=2, sticky="ew")
    controls = ttk.Frame(body)
    controls.grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)
    low, high = (tk.StringVar(value=f"{value:.3f}") for value in (ranges[0] if ranges else (0, 0)))
    status = tk.StringVar()
    playhead = tk.StringVar(value="Posição 0,00 s")
    ttk.Label(body, textvariable=status, style="Muted.TLabel", wraplength=475).grid(
        row=4, column=0, columnspan=2, sticky="w")
    ttk.Label(body, textvariable=playhead, style="Muted.TLabel").grid(
        row=4, column=1, sticky="e", padx=(8, 0))
    ready = []
    total = 0.
    request = None
    serial = 0
    pending = None
    busy = False
    playback = None
    poll_id = None
    messages = queue.SimpleQueue()

    def launch(kind, task):
        def run():
            try:
                messages.put((kind, task()))
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                messages.put((kind, error))
        threading.Thread(target=run, daemon=True).start()

    def request_frame(_=None):
        nonlocal request, serial, pending
        if not total:
            return
        serial += 1
        playhead.set(f"Posição {position.get():.2f} s".replace(".", ","))
        pending = (serial, max(0., min(position.get(), total - .07)))
        if request is not None:
            window.after_cancel(request)
        request = window.after(140, render_pending)

    def render_pending():
        nonlocal request, pending, busy
        request = None
        if busy or pending is None:
            return
        item, at = pending
        pending = None
        busy = True

        def read():
            try:
                return item, extract_frame(source, at)
            except (OSError, subprocess.SubprocessError):
                return item, None

        launch("frame", read)

    def poll():
        nonlocal total, busy, poll_id
        while not messages.empty():
            kind, value = messages.get()
            if kind == "probe":
                if isinstance(value, Exception):
                    status.set(f"Não foi possível abrir o vídeo. {value}")
                    continue
                total = value[0]
                slider.configure(to=total)
                if not ranges:
                    high.set(f"{min(total, 30.):.3f}")
                position.set(min(total, ranges[0][0] if ranges else 0))
                for control in ready:
                    control.state(["!disabled"])
                if segments is not None:
                    segments.configure(state="readonly")
                status.set(f"{total:.1f} s de vídeo · Arraste para ver um quadro.")
                request_frame()
            else:
                busy = False
                if not isinstance(value, Exception) and value[0] == serial:
                    try:
                        picture.image = tk.PhotoImage(master=window, data=value[1], format="ppm") if value[1] else None
                    except tk.TclError:
                        picture.image = None
                    picture.configure(image=picture.image or "",
                                      text="" if picture.image else "Quadro indisponível neste ponto")
                if request is None:
                    render_pending()
        poll_id = window.after(80, poll)

    def range_values():
        a, b = (parse_time(field.get().replace(",", ".")) for field in (low, high))
        if not math.isfinite(a + b) or not 0 <= a <= b - 1 or b > total + .001:
            raise ValueError("Escolha um trecho de pelo menos 1 s dentro do vídeo.")
        if active_index > 0 and a < drafts[active_index-1][1]:
            raise ValueError("O início sobrepõe o trecho anterior.")
        if active_index + 1 < len(drafts) and b > drafts[active_index+1][0]:
            raise ValueError("O fim sobrepõe o trecho seguinte.")
        return a, min(b, total)

    def select_segment(_event):
        nonlocal active_index
        new_index = segments.current()
        try:
            drafts[active_index] = range_values()
        except ValueError as error:
            segments.current(active_index)
            status.set(str(error))
            return
        active_index = new_index
        a, b = drafts[active_index]
        low.set(f"{a:.3f}")
        high.set(f"{b:.3f}")
        position.set(a)
        request_frame()

    if segments is not None:
        segments.bind("<<ComboboxSelected>>", select_segment)

    def stop_playing():
        nonlocal playback
        if playback and playback.poll() is None:
            playback.terminate()
        playback = None

    def play():
        nonlocal playback
        try:
            a, b = range_values()
            stop_playing()
            player = shutil.which("ffplay")
            if not player:
                raise ValueError("FFplay indisponível. A prévia por quadro continua disponível.")
            duration = min(12, b - a)
            playback = subprocess.Popen(
                [player, "-loglevel", "error", "-autoexit", "-threads", "1", "-filter_threads", "1",
                 "-ss", str(a), "-t", str(duration), "-x", "360", "-y", "360", str(source)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **child_options(force_low=True, hide=True))
            status.set(f"Tocando até {duration:.1f} s a partir do início marcado.")
        except (OSError, ValueError) as error:
            status.set(str(error))

    def apply():
        try:
            current = range_values()
            if drafts:
                drafts[active_index] = current
            marks = tuple(drafts) if drafts else (current,)
            if any(not math.isfinite(a+b) or a < 0 or b-a < 1 or b > total+.02 for a, b in marks):
                raise ValueError("O plano contém trechos fora do vídeo.")
            if sum(b-a for a, b in marks) > 180.01:
                raise ValueError("Escolha até 180 s de conteúdo por corte na prévia.")
            on_apply(marks)
            window.destroy()
        except ValueError as error:
            status.set(str(error))

    for label, variable in (("Início", low), ("Fim", high)):
        ttk.Label(controls, text=label).pack(side="left")
        ttk.Entry(controls, width=9, textvariable=variable).pack(side="left", padx=4)
        button = ttk.Button(controls, text="Marcar aqui",
                            command=lambda target=variable: target.set(f"{position.get():.3f}"))
        button.pack(side="left", padx=(0, 9))
        ready.append(button)
    play_button = ttk.Button(controls, text="Ouvir e ver 12 s", command=play)
    play_button.pack(side="left")
    apply_button = ttk.Button(controls, text="Usar corte", command=apply, style="Primary.TButton")
    apply_button.pack(side="right")
    ready.extend((play_button, apply_button))
    for control in ready:
        control.state(["disabled"])
    slider.configure(command=request_frame)
    def cleanup(event):
        if event.widget is window:
            for callback in (poll_id, request):
                if callback is not None:
                    window.after_cancel(callback)
            stop_playing()

    window.bind("<Destroy>", cleanup)
    launch("probe", lambda: probe(source, timeout=10))
    poll()
    return window


def select_plan(parent):
    filename = filedialog.askopenfilename(parent=parent, title="Abrir plano de cortes",
                                          filetypes=[("Plano JSON do Clip Studio", "*.json")])
    if not filename:
        return None
    path = Path(filename)
    if path.stat().st_size > 8 * 1024**2:
        raise ValueError("Escolha um plano de cortes do Clip Studio.")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("schema") != 1:
        raise ValueError("Arquivo de plano inválido.")
    try:
        source = Path(report["original_source"])
        clips = [tuple((float(part["start"]), float(part["end"])) for part in clip["parts"])
                 for clip in report["clips"]]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Arquivo de plano inválido.") from error
    clips = [parts for parts in clips if parts]
    if not source.is_file() or not clips:
        raise ValueError("O plano precisa de um arquivo de origem disponível e de pelo menos um corte.")
    return source, clips
