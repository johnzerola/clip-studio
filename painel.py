"""Painel Windows do Clip Studio."""
import json
import os
import queue
import shutil
import sqlite3
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from broll_library import library_items
from painel_visual import open_library, open_styles
from engine import Options, crop, live_source
from editorial import Cleanup
from live_scout import ScoutSettings
from runtime_profile import PROFILES, configure
import tema

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "resultados"
STYLES = {"Dinâmico": "dynamic", "Rosto em cima + jogo embaixo": "split",
          "Reação em tela + jogo no canto": "reaction", "Exportar os três estilos": "all",
          "Jogo em tela + facecam redonda": "gamecam"}
LOOKS = {"Shorts GTA": "shorts", "Clássico": "classic"}
MUSIC_MODES = ("Trilha automática", "Sem trilha", "Escolher arquivo")
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
        self.appearance = tk.StringVar(value="Sistema")
        self.review_layout = tk.StringVar(value="Galeria")
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
        self.workers = tk.IntVar(value=1)
        self.performance = tk.StringVar(value=PROFILES["leve"].label)
        self.session_status = tk.StringVar(value="Aguardando início")
        self.captions = tk.BooleanVar(value=True)
        self.channel_handle = tk.StringVar()
        self.autopilot = None
        self.hook_text = tk.StringVar()
        self.creative_effects = tk.BooleanVar(value=False)
        self.smart_reframe = tk.BooleanVar(value=False)
        self.montage = tk.BooleanVar(value=True)
        self.auto_face = tk.BooleanVar(value=True)
        self.look = tk.StringVar(value="Shorts GTA")
        self.hook = tk.BooleanVar(value=True)
        self.scout_live = tk.BooleanVar(value=True)
        self.scout_model = tk.StringVar(value="qwen3:4b")
        self.vision_model = tk.StringVar()
        self.scout_threshold = tk.IntVar(value=60)
        self.scout_cleanup = tk.BooleanVar(value=True)
        self.trim_live = tk.BooleanVar(value=True)
        self.scout_review = tk.BooleanVar(value=True)
        self.scout_continuous = tk.BooleanVar(value=True)
        self.scout_catchup = tk.BooleanVar(value=True)
        self.compression = tk.StringVar(value="compacto")
        self.replay_count = tk.IntVar(value=0)
        self.replay_period = tk.IntVar(value=0)
        self.replay_only = tk.BooleanVar(value=False)
        self.replay_gib = tk.IntVar(value=12)
        self.live_poll_hours = tk.IntVar(value=1)
        self.recording_transcript = tk.BooleanVar(value=True)
        self.convert_live_link = tk.BooleanVar(value=False)
        self.polish = tk.BooleanVar(value=True)
        self.voice_polish = tk.BooleanVar(value=True)
        self.music_mode = tk.StringVar(value=MUSIC_MODES[0])
        self.music = tk.StringVar()
        self.music_db = tk.IntVar(value=-25)
        self.transition = tk.StringVar(value="v9")
        self.sfx = tk.StringVar(value="auto")
        self.sfx_peak = tk.IntVar(value=-8)
        self.broll_dir = tk.StringVar()
        self.broll_selected = set()
        self.broll_count = tk.StringVar()
        self.broll_window = None
        self.style_window = None
        self.trim_window = None
        self.jobs_window = None
        self.visual_trim = None
        self.close_focus = tk.DoubleVar(value=.5)
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
            "appearance", "review_layout", "preset", "style", "corner", "face", "game", "duration", "count", "minutes", "workers", "performance",
            "captions", "channel_handle", "creative_effects", "smart_reframe", "montage", "silence", "repeats", "fillers", "speech", "pause", "noise", "auto_face",
            "speech_gaps", "wait_minutes", "output_dir", "look", "hook", "polish", "broll_dir", "close_focus",
            "scout_live", "scout_model", "vision_model", "scout_threshold", "scout_cleanup", "scout_review",
            "scout_continuous", "scout_catchup", "compression", "trim_live",
            "replay_count", "replay_period", "replay_only", "replay_gib", "live_poll_hours", "recording_transcript",
            "voice_polish", "music_mode", "music", "music_db", "transition", "sfx", "sfx_peak")}
        source_text = ""
        migrate_broll = False
        try:
            saved = json.loads(PREFERENCES.read_text(encoding="utf-8"))
            if isinstance(saved.get("sources_text"), str):
                source_text = saved["sources_text"]
            migrate_broll = "broll_selected" not in saved and bool(saved.get("broll_dir"))
            saved_broll = saved.get("broll_selected", [])
            if isinstance(saved_broll, list):
                self.broll_selected.update(key for key in saved_broll if isinstance(key, str))
            if "music_mode" not in saved and saved.get("music"):
                self.music_mode.set(MUSIC_MODES[2])
            for key, value in saved.items():
                if key in self.saved_fields:
                    self.saved_fields[key].set(value)
        except (OSError, ValueError, AttributeError, tk.TclError):
            pass
        if self.appearance.get() not in tema.MODES:
            self.appearance.set("Sistema")
        if self.review_layout.get() not in ("Galeria", "Sala de revisão"):
            self.review_layout.set("Galeria")
        if migrate_broll:
            self.broll_selected.update(asset.key for asset in self.library_assets() if asset.group == "Minha pasta")
        self.update_broll_count()
        root.title("Clip Studio • Lives, VODs e arquivos")
        tema.apply(root, self.appearance.get())
        root.geometry("1230x810")
        root.minsize(990, 700)
        shell = ttk.Frame(root)
        shell.pack(fill="both", expand=True)
        sidebar = ttk.Frame(shell, style="Nav.TFrame", padding=(12, 17))
        sidebar.pack(side="left", fill="y")
        ttk.Label(sidebar, text="Clip Studio", style="Brand.TLabel",
                  font=("Segoe UI Semibold", 20), padding=(8, 0, 10, 18)).pack(fill="x")
        workspace = ttk.Frame(shell)
        workspace.pack(side="left", fill="both", expand=True)
        top = ttk.Frame(workspace, padding=(18, 9))
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.session_status, style="Muted.TLabel").pack(side="left")
        from modelar_bridge import show_dialog
        ttk.Button(top, text="Modelar…", command=lambda: show_dialog(root, self.output_path)).pack(side="right", padx=8)
        theme_choice = ttk.Combobox(top, textvariable=self.appearance, values=tema.MODES,
                                    width=9, state="readonly")
        theme_choice.pack(side="right")
        ttk.Label(top, text="Tema", style="Muted.TLabel").pack(side="right", padx=(0, 7))
        ttk.Separator(workspace).pack(fill="x")
        frame = ttk.Frame(workspace, padding=(18, 9, 18, 12))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(14, weight=1)
        source_card = ttk.Frame(frame, padding=(12, 10), style="Card.TFrame")
        source_card.grid(row=0, column=0, columnspan=3, sticky="ew")
        source_card.columnconfigure(0, weight=1)
        ttk.Label(source_card, text="Fontes", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(source_card, text="Um link ou arquivo por linha. Twitch, Kick, YouTube, TikTok e X.",
                  style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 7))
        self.sources = tk.Text(source_card, height=3, font=("Segoe UI", 10), wrap="none",
                               bg=tema.PAPER, fg=tema.INK, insertbackground=tema.INK, relief="flat",
                               highlightthickness=1, highlightbackground=tema.active["line"], highlightcolor=tema.TEAL)
        self.sources.grid(row=2, column=0, sticky="ew")
        self.sources.insert("1.0", source_text)
        ttk.Button(source_card, text="Adicionar arquivos…", command=self.add_files).grid(row=2, column=1, sticky="n", padx=(10, 0))
        ttk.Button(source_card, text="Ajustar corte…", command=self.show_trim).grid(
            row=3, column=0, sticky="w", pady=(7, 0))
        ttk.Button(source_card, text="Abrir plano…", command=lambda: self.show_trim(from_plan=True)).grid(
            row=3, column=1, sticky="ew", padx=(10, 0), pady=(7, 0))
        workspace_style = ttk.Style(root)
        workspace_style.layout("Workspace.TNotebook.Tab", [])
        tabs = ttk.Notebook(frame, style="Workspace.TNotebook")
        tabs.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        home, editorial, audio_tab, auto_tab, ready_tab, agenda_tab = [
            ttk.Frame(tabs, padding=(3, 6)) for _ in range(6)
        ]
        navigation = ((home, "Visão geral"), (auto_tab, "Lives e gravações"), (editorial, "Edição"),
                      (audio_tab, "Som e B-roll"), (ready_tab, "Postagens"), (agenda_tab, "Agenda"))
        buttons = {}
        for tab, title in navigation:
            tabs.add(tab, text=title)
            button = ttk.Button(sidebar, text=title, command=lambda page=tab: tabs.select(page),
                                style="Nav.TButton", width=17)
            button.pack(fill="x", pady=2)
            buttons[str(tab)] = button
        from agenda_panel import Agenda
        from dashboard import Dashboard
        from publish_panel import PublishTab
        self.dashboard = Dashboard(home, self.output_path, lambda: tabs.select(auto_tab),
                                   lambda: tabs.select(ready_tab), self.open_posting)
        self.publish_tab = PublishTab(ready_tab, self.output_path, self.open_posting, self.scout_model.get,
                                      self.configure_autopilot, self.review_layout, self.save_preferences)
        self.agenda = Agenda(agenda_tab, self.output_path, lambda: tabs.select(ready_tab))

        def apply_theme(save=False):
            tema.apply(root, self.appearance.get())
            palette = tema.active
            self.sources.configure(bg=tema.PAPER, fg=tema.INK, insertbackground=tema.INK,
                                   highlightbackground=palette["line"], highlightcolor=palette["focus"])
            self.logs.configure(bg=palette["media"], fg=palette["media_text"])
            self.publish_tab.gallery.theme_changed()
            if save:
                self.save_preferences()

        def follow_system():
            if self.appearance.get() == "Sistema" and tema.resolve("Sistema") is not tema.active:
                apply_theme()
            root.after(3500, follow_system)

        def navigate(_event=None):
            current = tabs.select()
            for key, button in buttons.items():
                button.configure(style="NavActive.TButton" if key == current else "Nav.TButton")
            if current != str(ready_tab):
                self.publish_tab.gallery.player.stop()
            if current in (str(home), str(ready_tab), str(agenda_tab)):
                source_card.grid_remove()
                quick.grid_remove()
                if not self.active:
                    bar.grid_remove()
                    self.logs.grid_remove()
            else:
                source_card.grid()
                quick.grid()
                bar.grid()
                self.logs.grid()
            if current == str(ready_tab):
                self.publish_tab.refresh()
            elif current == str(home):
                self.dashboard.refresh()
            elif current == str(agenda_tab):
                self.agenda.refresh()

        tabs.bind("<<NotebookTabChanged>>", navigate)
        tabs.select(home)
        self.advanced = tk.Toplevel(root)
        self.advanced.withdraw()
        self.advanced.title("Configurações avançadas")
        self.advanced.protocol("WM_DELETE_WINDOW", self.advanced.withdraw)
        framing = ttk.Frame(self.advanced, padding=(16, 14))
        framing.pack(fill="both", expand=True)
        framing.columnconfigure(1, weight=1)
        self.field(framing, 0, "Recorte da webcam", ttk.Entry(framing, textvariable=self.face))
        self.field(framing, 1, "Recorte do jogo", ttk.Entry(framing, textvariable=self.game))
        self.field(framing, 2, "Canto da webcam", ttk.Combobox(framing, textvariable=self.corner,
                                                   values=("direito", "esquerdo"), state="readonly"))
        self.field(framing, 3, "Cortes manuais", ttk.Entry(framing, textvariable=self.manual))
        ttk.Label(framing, text="Recortes manuais em valores de 0 a 1. Exemplo de trecho: 1:25-1:40.").grid(
            row=4, column=0, columnspan=3, sticky="w")
        quick = ttk.Frame(frame)
        quick.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(11, 0))
        ttk.Label(quick, text="Estilo").pack(side="left")
        ttk.Button(quick, text="Ver e escolher…", command=self.show_styles).pack(side="left", padx=(6, 7))
        ttk.Label(quick, textvariable=self.style, wraplength=145, justify="left").pack(side="left", padx=(0, 14))
        ttk.Label(quick, text="Desempenho").pack(side="left")
        ttk.Combobox(quick, textvariable=self.performance, values=[p.label for p in PROFILES.values()],
                     state="readonly", width=27).pack(side="left", padx=(6, 15))
        ttk.Checkbutton(quick, text="Legendas", variable=self.captions).pack(side="left")
        ttk.Checkbutton(quick, text="Detectar webcam", variable=self.auto_face).pack(side="left", padx=8)
        brand = ttk.Frame(editorial)
        brand.grid(row=8, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Label(brand, text="@ do canal").pack(side="left")
        ttk.Entry(brand, textvariable=self.channel_handle, width=23).pack(side="left", padx=8)
        ttk.Label(brand, text="Assinatura no vídeo. Deixe vazio se preferir.", style="Muted.TLabel").pack(side="left")
        creative = ttk.Frame(editorial)
        creative.grid(row=9, column=0, columnspan=5, sticky="w", pady=(8,0))
        ttk.Label(creative, text="Gancho personalizado").pack(side="left")
        ttk.Entry(creative, textvariable=self.hook_text, width=26).pack(side="left", padx=8)
        ttk.Checkbutton(creative, text="Efeitos por IA", variable=self.creative_effects).pack(side="left", padx=(2,7))
        ttk.Checkbutton(creative, text="Reenquadrar rosto 9:16", variable=self.smart_reframe).pack(side="left")
        settings = ttk.Frame(editorial)
        settings.grid(row=4, columnspan=5, sticky="w", pady=(5, 0))
        for label, val, low, high in [("Duração (s)", self.duration, 10, 180), ("Clipes por trecho", self.count, 1, 8)]:
            ttk.Label(settings, text=label).pack(side="left", padx=(0, 3))
            ttk.Spinbox(settings, textvariable=val, from_=low, to=high, width=4).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(settings, text="Montagem de 3 momentos", variable=self.montage).pack(side="left")
        preset = ttk.Combobox(editorial, textvariable=self.preset, values=list(EDIT_PRESETS),
                              state="readonly", width=14)
        preset.grid(row=0, column=0, sticky="w", padx=(0, 10))
        preset.bind("<<ComboboxSelected>>", self.apply_preset)
        for column, (label, variable) in enumerate([
            ("Cortar silêncio", self.silence), ("Tirar repetições", self.repeats),
            ("Tirar hesitações", self.fillers), ("Juntar pela fala", self.speech)], 1):
            ttk.Checkbutton(editorial, text=label, variable=variable).grid(row=0, column=column, sticky="w", padx=5)
        levels = ttk.Frame(framing)
        levels.grid(row=5, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(levels, text="Pausa mínima (s)").pack(side="left")
        ttk.Spinbox(levels, textvariable=self.pause, from_=.3, to=5, increment=.1, width=5).pack(side="left", padx=(4, 15))
        ttk.Label(levels, text="Limiar (dBFS)").pack(side="left")
        ttk.Spinbox(levels, textvariable=self.noise, from_=-65, to=-18, width=5).pack(side="left", padx=4)
        ttk.Checkbutton(levels, text="Encurtar pausas sem fala", variable=self.speech_gaps).pack(side="left", padx=12)
        limits = ttk.Frame(framing)
        limits.grid(row=7, columnspan=5, sticky="w", pady=(6, 0))
        for label, value, low, high in (("Aguardar início (min)", self.wait_minutes, 0, 180),
                                         ("Captura (min, 0 = contínua)", self.minutes, 0, 720),
                                         ("Renderizações", self.workers, 1, 4)):
            ttk.Label(limits, text=label).pack(side="left", padx=(0, 4))
            ttk.Spinbox(limits, textvariable=value, from_=low, to=high, width=4).pack(side="left", padx=(0, 12))
        design = ttk.Frame(editorial)
        design.grid(row=2, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(design, text="Visual").pack(side="left")
        ttk.Combobox(design, textvariable=self.look, values=list(LOOKS), state="readonly",
                     width=15).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(design, text="Gancho inicial da fala", variable=self.hook).pack(side="left")
        ttk.Checkbutton(design, text="Transições e som", variable=self.polish).pack(side="left", padx=10)
        focus_line = ttk.Frame(framing)
        focus_line.grid(row=6, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(focus_line, text="Posição horizontal do rosto (0 a 1)").pack(side="left")
        ttk.Spinbox(focus_line, textvariable=self.close_focus, from_=0, to=1, increment=.05,
                    width=5).pack(side="left", padx=4)
        inserts = ttk.Frame(audio_tab)
        inserts.grid(row=2, columnspan=5, sticky="ew", pady=(7, 0))
        ttk.Button(inserts, text="Abrir biblioteca de B-roll…", command=self.show_library).pack(side="left")
        ttk.Label(inserts, textvariable=self.broll_count).pack(side="left", padx=10)
        live = ttk.Frame(framing)
        live.grid(row=8, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(live, text="Modelo Ollama").pack(side="left")
        ttk.Entry(live, textvariable=self.scout_model, width=15).pack(side="left", padx=4)
        ttk.Label(live, text="Nota mínima dos cortes").pack(side="left", padx=(8, 4))
        ttk.Spinbox(live, textvariable=self.scout_threshold, from_=20, to=95, width=4).pack(side="left")
        ttk.Label(live, text="Formato").pack(side="left", padx=(12, 4))
        ttk.Combobox(live, textvariable=self.compression, values=("original", "compacto", "hevc"),
                     width=9, state="readonly").pack(side="left")
        sound = ttk.Frame(audio_tab)
        sound.grid(row=0, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Checkbutton(sound, text="Melhorar clareza da voz", variable=self.voice_polish).pack(side="left")
        modes = ttk.Combobox(sound, textvariable=self.music_mode, values=MUSIC_MODES, state="readonly", width=20)
        modes.pack(side="left", padx=(12, 4))
        self.music_button = ttk.Button(sound, command=self.pick_music)
        modes.bind("<<ComboboxSelected>>", self.change_music_mode)
        self.update_music_button()
        bank = ttk.Frame(framing)
        bank.grid(row=9, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(bank, text="Transição").pack(side="left")
        ttk.Combobox(bank, textvariable=self.transition, values=("v9", "zoom", "linha", "corte"),
                     state="readonly", width=9).pack(side="left", padx=4)
        ttk.Label(bank, text="Efeito").pack(side="left", padx=(8, 0))
        ttk.Combobox(bank, textvariable=self.sfx, values=("auto", "whoosh", "radio", "impacto", "resolucao", "nenhum"),
                     state="readonly", width=11).pack(side="left", padx=4)
        ttk.Label(auto_tab, text="Lives em andamento",
                  font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w")
        monitor_options = ttk.Frame(auto_tab)
        monitor_options.grid(row=1, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Checkbutton(monitor_options, text="Aguardar novas lives", variable=self.scout_continuous).pack(side="left")
        ttk.Checkbutton(monitor_options, text="Procurar melhores momentos", variable=self.scout_live).pack(side="left", padx=10)
        ttk.Checkbutton(monitor_options, text="Revisar vídeo pronto", variable=self.scout_review).pack(side="left")
        ttk.Label(monitor_options, text="Buscar nova live a cada (h)").pack(side="left", padx=(12, 4))
        ttk.Combobox(monitor_options, values=(0, 1, 2, 3), textvariable=self.live_poll_hours,
                     width=4, state="readonly").pack(side="left")
        ttk.Label(bank, text="Pico (dBFS)").pack(side="left", padx=(8, 0))
        ttk.Spinbox(bank, textvariable=self.sfx_peak, from_=-24, to=-3, width=4).pack(side="left", padx=4)
        ttk.Label(bank, text="Volume da trilha (dB)").pack(side="left", padx=(12, 3))
        ttk.Spinbox(bank, textvariable=self.music_db, from_=-45, to=-12, width=4).pack(side="left")
        storage = ttk.Frame(framing)
        storage.grid(row=10, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Checkbutton(storage, text="Tentar incluir o início da live", variable=self.scout_catchup).pack(side="left")
        ttk.Checkbutton(storage, text="Liberar espaço após exportar", variable=self.scout_cleanup).pack(side="left", padx=8)
        ttk.Label(storage, text="Limite por gravação (GB)").pack(side="left")
        ttk.Combobox(storage, values=(3, 6, 12, 24, 48), textvariable=self.replay_gib, width=4,
                     state="readonly").pack(side="left", padx=4)
        ttk.Label(auto_tab, text="Lives que já terminaram",
                  font=("Segoe UI Semibold", 10)).grid(row=2, column=0, sticky="w", pady=(10, 0))
        archive = ttk.Frame(auto_tab)
        archive.grid(row=3, columnspan=5, sticky="w", pady=(4, 0))
        for label, variable, values, width in (
                ("Quantas buscar por canal", self.replay_count, (0, 2, 3), 4),
                ("Repetir busca a cada (h)", self.replay_period, (0, 1, 2, 3), 4)):
            ttk.Label(archive, text=label).pack(side="left")
            ttk.Combobox(archive, values=values, textvariable=variable, width=width,
                         state="readonly").pack(side="left", padx=(4, 12))
        archive_help = ttk.Frame(auto_tab)
        archive_help.grid(row=4, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Checkbutton(archive_help, text="Só lives que já terminaram", variable=self.replay_only).pack(side="left")
        ttk.Checkbutton(archive_help, text="Remover esperas sem fala nem ação", variable=self.trim_live).pack(side="left", padx=8)
        ttk.Label(archive_help, text="0 gravações = desativado. 0 h = buscar gravações uma vez.",
                  style="Muted.TLabel").pack(side="left", padx=8)
        recordings = ttk.Frame(auto_tab)
        recordings.grid(row=5, columnspan=5, sticky="w", pady=(7, 0))
        ttk.Checkbutton(recordings, text="Transcrever a gravação inteira e selecionar cortes com Ollama",
                        variable=self.recording_transcript).pack(side="left")
        ttk.Label(recordings, text="Use o link direto da gravação ou um arquivo.",
                  style="Muted.TLabel").pack(side="left", padx=8)
        recording_actions = ttk.Frame(auto_tab)
        recording_actions.grid(row=6, columnspan=5, sticky="w", pady=(8,0))
        ttk.Button(recording_actions, text="Abrir transcrição…", command=self.open_transcription).pack(side="left")
        ttk.Checkbutton(recording_actions, text="Links /live/ID do YouTube já terminaram",
                        variable=self.convert_live_link).pack(side="left", padx=9)
        visual_options = ttk.Frame(framing)
        visual_options.grid(row=11,columnspan=5,sticky="ew",pady=(5,0))
        ttk.Label(visual_options,text="Modelo visual Ollama (opcional)").pack(side="left")
        ttk.Entry(visual_options,textvariable=self.vision_model,width=45).pack(side="left",padx=8)
        ttk.Label(frame, text="Pasta de saída").grid(row=12, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.output_dir).grid(row=12, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(frame, text="Escolher pasta…", command=self.pick_output).grid(row=12, column=2, padx=8, pady=(8, 0))
        bar = ttk.Frame(frame)
        bar.grid(row=13, columnspan=3, sticky="ew", pady=8)
        self.buttons = []
        for name, render in [("Gerar clipes com edição", True), ("Gerar só o plano de cortes", False)]:
            button = ttk.Button(bar, text=name, command=lambda state=render: self.start(state),
                                style="Primary.TButton" if render else "TButton")
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)
        self.stop_button = ttk.Button(bar, text="Parar trabalho", command=self.stop.set, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Button(bar, text="Abrir resultados", command=self.open_output).pack(side="right")
        ttk.Button(bar, text="Fila de postagem", command=self.open_posting).pack(side="right", padx=8)
        ttk.Button(frame, text="Trabalhos CLI/MCP…", command=self.open_jobs).grid(
            row=14, column=1, sticky="e", padx=(0, 10), pady=(0, 5))
        ttk.Button(frame, text="Configurações avançadas…", command=self.show_advanced).grid(
            row=14, column=2, sticky="e", pady=(0, 5))
        frame.rowconfigure(14, weight=0)
        frame.rowconfigure(15, weight=1)
        self.logs = tk.Text(frame, height=8, state="disabled", wrap="word", bg="#152b33", fg="#d7edeb",
                            font=("Consolas", 10), padx=12, pady=9, relief="flat")
        self.logs.grid(row=15, columnspan=3, sticky="nsew")
        root.after_idle(navigate)
        root.after_idle(apply_theme)
        root.after(3500, follow_system)
        theme_choice.bind("<<ComboboxSelected>>", lambda _: apply_theme(save=True))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(150, self.poll)
        root.after(1800, self.check_for_updates)

    def check_for_updates(self):
        from update_check import check_for_update
        if not hasattr(self, "update_events"):
            self.update_events = queue.Queue()
            self.update_seen = set()
        check_for_update(self.update_events.put)
        self.root.after(900000, self.check_for_updates)
        if not getattr(self, "update_poll_started", False):
            self.update_poll_started = True
            self.root.after(500, self.poll_updates)

    def update_busy(self):
        from job_registry import list_jobs
        if self.active or self.publish_tab.busy:
            return True
        return any(row["state"] in ("queued", "running") for row in list_jobs())

    def poll_updates(self):
        try:
            busy = self.update_busy()
        except (OSError, sqlite3.Error):
            busy = True
        if not busy:
            try:
                release = self.update_events.get_nowait()
            except queue.Empty:
                pass
            else:
                tag = release.get("tag_name", "")
                if tag not in self.update_seen:
                    self.update_seen.add(tag)
                    self.offer_update(release)
        if self.root.winfo_exists():
            self.root.after(2000, self.poll_updates)

    def offer_update(self, release):
        from update_install import start_update, select_assets
        tag = release.get("tag_name", "")
        notes = str(release.get("body") or "Melhorias e correções do Clip Studio.")[:1800]
        try:
            select_assets(release)
        except ValueError:
            # A release pode estar entre a publicação e o envio dos anexos.
            self.update_seen.discard(tag)
            return
        if messagebox.askyesno("Atualização disponível",
            f"Clip Studio {tag}\n\n{notes}\n\n"
            "Atualizar agora? O painel será fechado, a atualização será instalada e o app abrirá novamente. "
            "A instalação anterior será preservada.", parent=self.root):
            try:
                if self.update_busy():
                    messagebox.showinfo("Atualização", "Aguarde os trabalhos em andamento terminarem.", parent=self.root)
                    self.update_seen.discard(tag)
                    return
                self.save_preferences()
                self.publish_tab.gallery.player.stop()
                start_update(ROOT, release)
                self.root.destroy()
            except (OSError, ValueError) as error:
                messagebox.showerror("Atualização", str(error), parent=self.root)

    @staticmethod
    def field(frame, row, label, widget):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)

    def apply_preset(self, _event=None):
        for variable, value in zip(self.editor_fields, EDIT_PRESETS[self.preset.get()]):
            variable.set(value)

    def save_preferences(self):
        draft = PREFERENCES.with_suffix(".tmp")
        state = {key: variable.get() for key, variable in self.saved_fields.items()}
        state["broll_selected"] = sorted(self.broll_selected)
        state["sources_text"] = self.sources.get("1.0", "end-1c")
        draft.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
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

    def pick_broll(self):
        folder = filedialog.askdirectory(initialdir=self.broll_dir.get() or str(ROOT))
        if folder:
            self.broll_dir.set(folder)

    def library_assets(self):
        return library_items(ROOT / "biblioteca.local", self.broll_dir.get().strip(),
                             included=ROOT / "biblioteca")

    def update_broll_count(self):
        count = sum(asset.key in self.broll_selected for asset in self.library_assets()) if self.broll_selected else 0
        label = "1 item selecionado" if count == 1 else f"{count} itens selecionados"
        self.broll_count.set(label if count else "Selecione o que quer usar")

    def show_library(self):
        if self.broll_window and self.broll_window.winfo_exists():
            self.broll_window.lift()
            return
        self.broll_window = open_library(self.root, self.library_assets, self.broll_selected,
                                         self.pick_broll, self.update_broll_count)

    def show_advanced(self):
        self.advanced.deiconify()
        self.advanced.transient(self.root)
        self.advanced.lift()

    def show_styles(self):
        if self.style_window and self.style_window.winfo_exists():
            self.style_window.lift()
            return
        self.style_window = open_styles(self.root, self.style, STYLES)

    def update_music_button(self):
        custom = self.music_mode.get() == MUSIC_MODES[2]
        path = self.music.get().strip()
        name = Path(path).name if path else ""
        self.music_button.configure(text=(name[:30] + "…" if len(name) > 31 else name) or "Selecionar trilha…")
        if custom:
            self.music_button.pack(side="left", padx=3)
        else:
            self.music_button.pack_forget()

    def change_music_mode(self, _event=None):
        if self.music_mode.get() == MUSIC_MODES[2] and not self.music.get():
            if not self.pick_music():
                self.music_mode.set(MUSIC_MODES[0])
        self.update_music_button()

    def pick_music(self):
        path = filedialog.askopenfilename(filetypes=[("Áudio", "*.wav *.mp3 *.m4a *.aac *.ogg *.flac"), ("Todos", "*.*")])
        if path:
            self.music.set(path)
            self.update_music_button()
        return bool(path)

    def output_path(self):
        value = self.output_dir.get().strip().strip('"')
        if not value or not Path(value).is_absolute():
            raise ValueError("Escolha uma pasta de saída com caminho absoluto.")
        return Path(value).resolve()

    def open_transcription(self):
        path = filedialog.askopenfilename(parent=self.root, title="Abrir transcrição",
                                          initialdir=str(self.output_path()),
                                          filetypes=[("Transcrição por frase", "*.txt"), ("Palavras e tempos", "*.jsonl")])
        if path:
            os.startfile(path)

    def open_output(self):
        try:
            path = self.output_path()
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Pasta de saída", str(error))

    def show_trim(self, from_plan=False):
        from tkinter.simpledialog import askinteger
        from trim_preview import open_trim, select_plan

        if self.trim_window and self.trim_window.winfo_exists():
            self.trim_window.lift()
            return
        try:
            if from_plan:
                selected = select_plan(self.root)
                if not selected:
                    return
                source, clips = selected
                index = 1 if len(clips) == 1 else askinteger(
                    "Escolher corte", f"Qual corte do plano? Escolha de 1 a {len(clips)}.",
                    minvalue=1, maxvalue=len(clips), parent=self.root)
                if index is None:
                    return
                ranges = clips[index - 1]
            else:
                lines = [line.strip() for line in self.sources.get("1.0", "end").splitlines() if line.strip()]
                source = Path(lines[0].split("|")[0].strip().strip('"')) if len(lines) == 1 else None
                if not source or not source.is_file():
                    raise ValueError("Adicione um único vídeo local. Para uma live encerrada, use o arquivo já baixado.")
                ranges = parse_ranges(self.manual.get())

            def apply(marks):
                if from_plan:
                    self.sources.delete("1.0", "end")
                    self.sources.insert("1.0", str(source))
                self.manual.set(", ".join(f"{a:.3f}-{b:.3f}" for a, b in marks))
                self.visual_trim = (source.resolve(), self.manual.get())
                self.log("Corte ajustado. Use Gerar clipes com edição para exportar.")

            self.trim_window = open_trim(self.root, source, ranges, apply, parse_time)
        except (ValueError, OSError) as error:
            messagebox.showerror("Ajustar corte", str(error), parent=self.root)

    def open_jobs(self):
        from painel_jobs import open_jobs

        if self.jobs_window and self.jobs_window.winfo_exists():
            self.jobs_window.lift()
            return
        self.jobs_window = open_jobs(self.root)

    def configure_autopilot(self):
        from studio_panel import autopilot_dialog

        if self.active:
            messagebox.showinfo("Piloto automático", "Configure antes de iniciar a próxima captura ou edição.")
            return

        def apply(config):
            self.autopilot = config
            self.publish_tab.show_autopilot(config)
        autopilot_dialog(self.root, self.autopilot, apply)

    def open_posting(self):
        from posting_panel import show_queue

        try:
            if not self.active:
                configure(next((key for key, profile in PROFILES.items() if profile.label == self.performance.get()), "leve"))
            show_queue(self.root, self.output_path(), self.scout_model.get().strip(), self.scout_threshold.get())
        except (OSError, ValueError, tk.TclError) as error:
            messagebox.showerror("Fila de postagem", str(error), parent=self.root)

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
                self.session_status.set("Sessão encerrada · confira o registro abaixo")
                for button in self.buttons:
                    button.state(["!disabled"])
                self.stop_button.state(["disabled"])
            else:
                self.logs.configure(state="normal")
                self.logs.insert("end", message + "\n")
                if int(self.logs.index("end-1c").split(".")[0]) > 3500:
                    self.logs.delete("1.0", "501.0")
                self.logs.see("end")
                self.logs.configure(state="disabled")
        self.root.after(150, self.poll)

    def close(self):
        self.publish_tab.gallery.player.stop()
        if self.publish_tab.busy:
            messagebox.showinfo("Publicação em andamento", "Aguarde o resultado do YouTube antes de fechar.")
            return
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
                if not fields[0] or len(fields) > 4:
                    raise ValueError("Use fonte | rosto | jogo | centro do close. Só a fonte é obrigatória.")
                value, *regions = fields
                for region in regions[:2]:
                    crop(region)
                if len(regions) == 3 and not 0 <= float(regions[2]) <= 1:
                    raise ValueError("O centro do close por fonte deve estar entre 0 e 1.")
                path = Path(value)
                if "://" not in value and path.is_file():
                    sources.append((str(path.resolve()), "file", regions))
                else:
                    url, vod = live_source(value)
                    if self.convert_live_link.get() and url.startswith("https://www.youtube.com/live/"):
                        url, vod = url.replace("/live/", "/watch?v=", 1), True
                    sources.append((url, "vod" if vod else "live", regions))
            sources = list({(source, kind, tuple(regions)): (source, kind, regions)
                            for source, kind, regions in sources}.values())
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
            broll_assets = tuple((asset.path, asset.cues) for asset in self.library_assets()
                                 if asset.key in self.broll_selected) if self.broll_selected else ()
            focus = self.close_focus.get()
            if not 0 <= focus <= 1:
                raise ValueError("Use um centro de close de 0 a 1.")
            custom_music = self.music_mode.get() == MUSIC_MODES[2]
            music = self.music.get().strip() if custom_music else ""
            music_db = self.music_db.get()
            if custom_music and (not music or not Path(music).is_file()):
                raise ValueError("Escolha um arquivo de trilha existente.")
            if not -45 <= music_db <= -12:
                raise ValueError("Use volume da trilha entre -45 e -12 dB.")
            scout = ScoutSettings(self.scout_live.get(), self.scout_model.get().strip(),
                                  self.scout_threshold.get(), self.scout_cleanup.get(), duration,
                                  review_final=self.scout_review.get() and render,
                                  continuous=self.scout_continuous.get() and minutes == 0,
                                  catchup=self.scout_catchup.get(), replay_count=self.replay_count.get(),
                                  replay_period=self.replay_period.get(), replay_only=self.replay_only.get(),
                                  replay_gib=self.replay_gib.get(), live_poll_hours=self.live_poll_hours.get(),
                                  performance=next(key for key,p in PROFILES.items() if p.label == self.performance.get()),
                                  trim_inactive=self.trim_live.get(), vision_model=self.vision_model.get().strip(),
                                  transcribe_recordings=self.recording_transcript.get(), autopilot=self.autopilot)
            if scout.replay_count or scout.replay_period or scout.replay_only:
                from replay_library import archive_url
                if not lives or scout.replay_count not in (2, 3) or scout.replay_period not in (0, 1, 2, 3):
                    raise ValueError("Para buscar replays, escolha 2 ou 3 e adicione um canal.")
                if scout.replay_period and not render:
                    raise ValueError("O monitor de replays requer Gerar clipes com edição.")
                for url, kind, _ in sources:
                    if kind == "live":
                        archive_url(url)
            if not 20 <= scout.threshold <= 95:
                raise ValueError("Escolha uma nota de triagem entre 20 e 95.")
            if not -24 <= self.sfx_peak.get() <= -3:
                raise ValueError("Use pico dos efeitos entre -24 e -3 dBFS.")
            options = Options(style, face, game, self.corner.get(), self.captions.get(),
                              self.montage.get(), duration, count, render, manual, cleanup, self.auto_face.get(),
                              LOOKS[self.look.get()], self.hook.get(), self.polish.get(), "", focus,
                              self.voice_polish.get(), 130, music, music_db,
                              self.transition.get(), self.sfx.get(), self.sfx_peak.get(), self.compression.get(),
                              broll_assets=broll_assets, contextual_broll=False, channel_handle=self.channel_handle.get(),
                              hook_text=self.hook_text.get(),
                              effects_model=self.scout_model.get().strip() if self.creative_effects.get() else "",
                              smart_reframe=self.smart_reframe.get(),
                              auto_music=self.music_mode.get() == MUSIC_MODES[0],
                              keep_manual_edges=bool(manual and not lives and sources[0][1] == "file"
                                                     and self.visual_trim == (Path(sources[0][0]), self.manual.get())))
            try:
                self.save_preferences()
            except OSError as error:
                self.log(f"Preferências não salvas: {error}")
        except (KeyError, ValueError, OSError, StopIteration, tk.TclError) as error:
            messagebox.showerror("Revise os dados", str(error))
            return
        if render and not options.auto_face and any(not (regions[0] if regions else face) for _, _, regions in sources):
            self.log("Fontes sem recorte de facecam serão renderizadas no layout de gameplay.")
        self.active = True
        self.session_status.set("Sessão em andamento")
        self.stop.clear()
        for button in self.buttons:
            button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        threading.Thread(target=self.run, args=(sources, options, minutes, workers, output, wait_minutes, scout),
                         daemon=True).start()

    def run(self, sources, options, minutes, workers, output, wait_minutes, scout=ScoutSettings(False)):
        from job_registry import tracked_session

        try:
            tracked_session("Painel", sources, options, minutes, workers, output, wait_minutes,
                            self.stop, self.log, scout)
        except (OSError, RuntimeError) as error:
            self.log(str(error))
        finally:
            self.events.put(None)


if __name__ == "__main__":
    window = tk.Tk()
    Panel(window)
    window.mainloop()
