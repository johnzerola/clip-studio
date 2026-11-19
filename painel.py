"""Painel Windows do Clip Studio."""
import json
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

from engine import Options, capture, crop, fetch_vod, live_source, process
from editorial import Cleanup

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "resultados"
STYLES = {"Dinâmico": "dynamic", "Rosto em cima + jogo embaixo": "split",
          "Reação em tela + jogo no canto": "reaction", "Exportar os três estilos": "all",
          "Jogo em tela + facecam redonda": "gamecam"}
LOOKS = {"Shorts GTA": "shorts", "Clássico": "classic"}
PREFERENCES = ROOT / "preferencias.local.json"
EDIT_PRESETS = {
    "GTA / Reação": (True, True, True, True, 1.5, -42, False),
    "Conversa": (True, True, True, True, .9, -36, True),
    "Sem limpeza": (False, False, False, False, .9, -36, False),
}


def parse_time(value):
    import math
    components = [float(s) for s in value.split(":")]
    if not 1 <= len(components) <= 3 or any(not math.isfinite(s) or s < 0 for s in components):
        raise ValueError("Tempo inválido.")
    return sum(s * 60**i for i, s in enumerate(reversed(components)))


def parse_ranges(value):
    ranges = []
    for part in value.split(",") if value.strip() else []:
        a, b = [parse_time(s.strip()) for s in part.strip().split("-")]
        if b - a < 1 or (ranges and a < ranges[-1][1]):
            raise ValueError("Use intervalos de pelo menos 1 s, em ordem e sem sobreposição.")
        ranges.append((a, b))
    return tuple(ranges)


class Panel:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.active = False
        self.style = tk.StringVar(value=next(iter(STYLES)))
        self.corner = tk.StringVar(value="direito")
        self.face = tk.StringVar()
        self.game = tk.StringVar()
        self.manual = tk.StringVar()
        self.duration = tk.IntVar(value=90)
        self.count = tk.IntVar(value=2)
        self.minutes = tk.IntVar(value=0)
        self.wait_minutes = tk.IntVar(value=15)
        self.output_dir = tk.StringVar(value=str(OUTPUT))
        self.workers = tk.IntVar(value=2)
        self.captions = tk.BooleanVar(value=True)
        self.montage = tk.BooleanVar(value=True)
        self.auto_face = tk.BooleanVar(value=True)
        self.look = tk.StringVar(value="Shorts GTA")
        self.hook = tk.BooleanVar(value=True)
        self.preset = tk.StringVar(value="GTA / Reação")
        self.silence = tk.BooleanVar()
        self.repeats = tk.BooleanVar()
        self.fillers = tk.BooleanVar()
        self.speech = tk.BooleanVar()
        self.pause = tk.DoubleVar()
        self.noise = tk.IntVar()
        self.speech_gaps = tk.BooleanVar()
        self.editor_fields = (self.silence, self.repeats, self.fillers, self.speech, self.pause, self.noise,
                              self.speech_gaps)
        self.apply_preset()
        self.saved_fields = {key: getattr(self, key) for key in (
            "preset", "style", "corner", "face", "game", "duration", "count", "minutes", "workers",
            "captions", "montage", "silence", "repeats", "fillers", "speech", "pause", "noise", "auto_face",
            "speech_gaps", "wait_minutes", "output_dir", "look", "hook")}
        try:
            saved = json.loads(PREFERENCES.read_text(encoding="utf-8"))
            for key, value in saved.items():
                if key in self.saved_fields:
                    self.saved_fields[key].set(value)
        except (OSError, ValueError, AttributeError, tk.TclError):
            pass
        root.title("Clip Studio • Twitch e arquivos")
        root.geometry("980x860")
        root.minsize(850, 750)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(14, weight=1)
        ttk.Label(frame, text="Clip Studio", font=("Segoe UI", 22, "bold")).grid(row=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Uma fonte por linha: Twitch, link de live no X, VOD da Twitch ou vídeo local. "
                              "Até 8 lives.").grid(row=1, columnspan=3, sticky="w", pady=(4, 8))
        self.sources = tk.Text(frame, height=6, font=("Consolas", 11), wrap="none")
        self.sources.grid(row=2, columnspan=2, sticky="ew")
        ttk.Button(frame, text="Adicionar arquivos…", command=self.add_files).grid(row=2, column=2, sticky="n", padx=8)
        self.field(frame, 3, "Estilo", ttk.Combobox(frame, textvariable=self.style, values=list(STYLES), state="readonly"))
        self.field(frame, 4, "Facecam (opcional)", ttk.Entry(frame, textvariable=self.face))
        self.field(frame, 5, "Gameplay (opcional)", ttk.Entry(frame, textvariable=self.game))
        ttk.Label(frame, text="Recortes em x,y,largura,altura de 0 a 1. Por fonte: canal | rosto | jogo"
                  ).grid(row=6, column=1, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="Buscar facecam", variable=self.auto_face).grid(row=6, column=0, sticky="w")
        self.field(frame, 7, "Canto da janela", ttk.Combobox(frame, textvariable=self.corner,
                                                         values=("direito", "esquerdo"), state="readonly"))
        self.field(frame, 8, "Cortes manuais", ttk.Entry(frame, textvariable=self.manual))
        ttk.Label(frame, text="Ex.: 1:25-1:40, 1:48-2:00, 2:36-2:49 • para um VOD ou vídeo local"
                  ).grid(row=9, column=1, columnspan=2, sticky="w")
        settings = ttk.Frame(frame)
        settings.grid(row=10, columnspan=3, sticky="w", pady=(10, 5))
        for label, val, low, high in [("Duração (s)", self.duration, 10, 180), ("Clipes/bloco", self.count, 1, 8),
                                       ("Live (0 = sem limite)", self.minutes, 0, 720), ("Motores", self.workers, 1, 4)]:
            ttk.Label(settings, text=label).pack(side="left", padx=(0, 3))
            ttk.Spinbox(settings, textvariable=val, from_=low, to=high, width=4).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(settings, text="Montagem de 3 momentos", variable=self.montage).pack(side="left")
        ttk.Checkbutton(settings, text="Legendas", variable=self.captions).pack(side="left")
        editorial = ttk.LabelFrame(frame, text="Edição automática", padding=(8, 5))
        editorial.grid(row=11, columnspan=3, sticky="ew", pady=(5, 0))
        preset = ttk.Combobox(editorial, textvariable=self.preset, values=list(EDIT_PRESETS),
                              state="readonly", width=14)
        preset.grid(row=0, column=0, sticky="w", padx=(0, 10))
        preset.bind("<<ComboboxSelected>>", self.apply_preset)
        for column, (label, variable) in enumerate([
            ("Cortar silêncio", self.silence), ("Tirar repetições", self.repeats),
            ("Tirar hesitações", self.fillers), ("Juntar pela fala", self.speech)], 1):
            ttk.Checkbutton(editorial, text=label, variable=variable).grid(row=0, column=column, sticky="w", padx=5)
        levels = ttk.Frame(editorial)
        levels.grid(row=1, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(levels, text="Pausa mínima (s)").pack(side="left")
        ttk.Spinbox(levels, textvariable=self.pause, from_=.3, to=5, increment=.1, width=5).pack(side="left", padx=(4, 15))
        ttk.Label(levels, text="Limiar (dBFS)").pack(side="left")
        ttk.Spinbox(levels, textvariable=self.noise, from_=-65, to=-18, width=5).pack(side="left", padx=4)
        ttk.Checkbutton(levels, text="Encurtar pausas sem fala", variable=self.speech_gaps).pack(side="left", padx=12)
        ttk.Label(levels, text="Aguardar início (min)").pack(side="left")
        ttk.Spinbox(levels, textvariable=self.wait_minutes, from_=0, to=180, width=4).pack(side="left", padx=4)
        design = ttk.Frame(editorial)
        design.grid(row=2, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(design, text="Visual").pack(side="left")
        ttk.Combobox(design, textvariable=self.look, values=list(LOOKS), state="readonly",
                     width=15).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(design, text="Gancho inicial da fala", variable=self.hook).pack(side="left")
        ttk.Label(frame, text="Pasta de saída").grid(row=12, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.output_dir).grid(row=12, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(frame, text="Escolher pasta…", command=self.pick_output).grid(row=12, column=2, padx=8, pady=(8, 0))
        bar = ttk.Frame(frame)
        bar.grid(row=13, columnspan=3, sticky="ew", pady=8)
        self.buttons = []
        for name, render in [("Somente analisar", False), ("Analisar e renderizar", True)]:
            button = ttk.Button(bar, text=name, command=lambda state=render: self.start(state))
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)
        self.stop_button = ttk.Button(bar, text="Parar captura", command=self.stop.set, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Button(bar, text="Abrir resultados", command=self.open_output).pack(side="right")
        self.logs = tk.Text(frame, height=10, state="disabled", wrap="word")
        self.logs.grid(row=14, columnspan=3, sticky="nsew")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(150, self.poll)

    @staticmethod
    def field(frame, row, label, widget):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)

    def apply_preset(self, _event=None):
        for variable, value in zip(self.editor_fields, EDIT_PRESETS[self.preset.get()]):
            variable.set(value)

    def save_preferences(self):
        draft = PREFERENCES.with_suffix(".tmp")
        draft.write_text(json.dumps({key: variable.get() for key, variable in self.saved_fields.items()},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
        draft.replace(PREFERENCES)

    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.webm *.ts *.avi"),
                                                       ("Todos", "*.*")])
        for path in paths:
            self.sources.insert("end", path + "\n")

    def pick_output(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir.get() or str(ROOT))
        if folder:
            self.output_dir.set(folder)

    def output_path(self):
        value = self.output_dir.get().strip().strip('"')
        if not value or not Path(value).is_absolute():
            raise ValueError("Escolha uma pasta de saída com caminho absoluto.")
        return Path(value).resolve()

    def open_output(self):
        try:
            path = self.output_path()
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Pasta de saída", str(error))

    def log(self, message):
        self.events.put(str(message))

    def poll(self):
        while True:
            try:
                message = self.events.get_nowait()
            except queue.Empty:
                break
            if message is None:
                self.active = False
                for button in self.buttons:
                    button.state(["!disabled"])
                self.stop_button.state(["disabled"])
            else:
                self.logs.configure(state="normal")
                self.logs.insert("end", message + "\n")
                self.logs.see("end")
                self.logs.configure(state="disabled")
        self.root.after(150, self.poll)

    def close(self):
        if self.active:
            self.stop.set()
            messagebox.showinfo("Sessão em andamento", "Captura sinalizada para parar. "
                                "Aguarde os trabalhos já enfileirados antes de fechar.")
        else:
            try:
                self.save_preferences()
            except (OSError, tk.TclError):
                pass
            self.root.destroy()

    def start(self, render):
        try:
            sources = []
            for line in dict.fromkeys(s.strip().strip('"') for s in self.sources.get("1.0", "end").splitlines() if s.strip()):
                fields = [field.strip().strip('"') for field in line.split("|")]
                if not fields[0] or len(fields) > 3:
                    raise ValueError("Use uma fonte por linha, seguida opcionalmente de | rosto | jogo.")
                value, *regions = fields
                for region in regions:
                    crop(region)
                path = Path(value)
                if "://" not in value and path.is_file():
                    sources.append((str(path.resolve()), "file", regions))
                else:
                    url, vod = live_source(value)
                    sources.append((url, "vod" if vod else "live", regions))
            lives = sum(kind == "live" for _, kind, _ in sources)
            if not sources or lives > 8:
                raise ValueError("Informe pelo menos uma fonte. O limite é de 8 lives por rodada.")
            if not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe")):
                raise ValueError("Instale FFmpeg e FFprobe e adicione ao PATH.")
            face, game = self.face.get().strip(), self.game.get().strip()
            crop(face)
            crop(game)
            manual = parse_ranges(self.manual.get())
            if manual and (lives or len(sources) != 1):
                raise ValueError("Cortes manuais exigem um único VOD ou vídeo local.")
            duration, count, minutes, workers = (x.get() for x in
                                                  (self.duration, self.count, self.minutes, self.workers))
            wait_minutes = self.wait_minutes.get()
            if not (10 <= duration <= 180 and 1 <= count <= 8 and 0 <= minutes <= 720
                    and 1 <= workers <= 4 and 0 <= wait_minutes <= 180):
                raise ValueError("Revise duração, clipes por bloco, minutos e limite de motores.")
            output = self.output_path()
            output.mkdir(parents=True, exist_ok=True)
            style = STYLES[self.style.get()]
            if style == "all" and not self.auto_face.get() and any(
                    not (regions[0] if regions else face) for _, _, regions in sources):
                raise ValueError("Para exportar três estilos, informe o recorte de facecam de cada fonte.")
            cleanup = Cleanup(*(variable.get() for variable in self.editor_fields[:-1]),
                              speech_gaps=self.speech_gaps.get())
            if not (.3 <= cleanup.pause <= 5 and -65 <= cleanup.noise <= -18):
                raise ValueError("Use pausa entre 0,3 e 5 s e limiar entre -65 e -18 dBFS.")
            options = Options(style, face, game, self.corner.get(), self.captions.get(),
                              self.montage.get(), duration, count, render, manual, cleanup, self.auto_face.get(),
                              LOOKS[self.look.get()], self.hook.get())
            try:
                self.save_preferences()
            except OSError as error:
                self.log(f"Preferências não salvas: {error}")
        except (KeyError, ValueError, OSError, tk.TclError) as error:
            messagebox.showerror("Revise os dados", str(error))
            return
        if render and not options.auto_face and any(not (regions[0] if regions else face) for _, _, regions in sources):
            self.log("Fontes sem recorte de facecam serão renderizadas no layout de gameplay.")
        self.active = True
        self.stop.clear()
        for button in self.buttons:
            button.state(["disabled"])
        if lives:
            self.stop_button.state(["!disabled"])
        threading.Thread(target=self.run, args=(sources, options, minutes, workers, output, wait_minutes),
                         daemon=True).start()

    def run(self, sources, options, minutes, workers, output, wait_minutes):
        from dataclasses import replace
        batch = output / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6])
        errors = queue.SimpleQueue()

        def safely(task, *args):
            try:
                task(*args)
            except Exception as error:
                errors.put(str(error))
                self.log(f"Erro: {error}")

        try:
            batch.mkdir(parents=True)
            self.log(f"Sessão: {batch}")
            with (ThreadPoolExecutor(max_workers=workers) as analysis,
                  ThreadPoolExecutor(max_workers=8) as lives, ThreadPoolExecutor(max_workers=2) as downloads):
                def schedule(path, folder, settings):
                    analysis.submit(safely, process, path, folder, settings, self.log)

                def vod(url, folder, result, settings):
                    self.log(f"Baixando VOD: {url}")
                    schedule(fetch_vod(sys.executable, url, folder), result, settings)

                def schedule_live(path, block, capture_dir, result, settings):
                    schedule(path, result / block.relative_to(capture_dir), settings)

                futures = []
                from functools import partial
                for i, (source, kind, regions) in enumerate(sources, 1):
                    source_name = f"{i:02}_{kind}"
                    result = batch / "Clipes prontos" / source_name
                    settings = replace(options, **dict(zip(("face", "game"), regions)))
                    if kind == "file":
                        schedule(Path(source), result, settings)
                    else:
                        folder = batch / "Capturas" / source_name
                        folder.mkdir(parents=True)
                        if kind == "vod":
                            futures.append(downloads.submit(safely, vod, source, folder, result, settings))
                        else:
                            futures.append(lives.submit(safely, capture, sys.executable, source, folder,
                                                        minutes, partial(schedule_live, capture_dir=folder,
                                                                         result=result, settings=settings),
                                                        self.stop, self.log, wait_minutes))
                for future in futures:
                    future.result()
            self.log("Sessão concluída." if errors.empty() else "Sessão encerrada com erros. Consulte o registro.")
        except Exception as error:
            self.log(f"Sessão interrompida: {error}")
        finally:
            self.events.put(None)


if __name__ == "__main__":
    window = tk.Tk()
    Panel(window)
    window.mainloop()
