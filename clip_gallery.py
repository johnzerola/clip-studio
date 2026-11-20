"""Editorial gallery with a single selected clip and two preview layouts."""
import queue
import threading
import tkinter as tk
from collections import OrderedDict
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

from local_preview import Preview
from painel_visual import thumbnail
import tema

PAGE_SIZE = 3


class ClipGallery:
    def __init__(self, frame, preview, explain, schedule, studio, layout):
        self.frame = frame
        self.layout = layout
        self.page = 0
        self.items = []
        self.cache = OrderedDict()
        self.result = queue.SimpleQueue()
        self.inflight = set()
        self.images = {}
        self.boxes = {}
        self.selected = None
        self.preview_photo = None
        self.animation = None

        deck = self.house = ttk.Frame(frame)
        deck.pack(fill="x", pady=(6, 0))
        deck.columnconfigure(0, weight=1)
        deck.columnconfigure(1, minsize=305)
        self.listing = ttk.Frame(deck)
        self.strip = ttk.Frame(self.listing)
        self.strip.pack(fill="x")
        bar = ttk.Frame(self.listing)
        bar.pack(fill="x", pady=(8, 0))
        self.previous = ttk.Button(bar, text="Anterior", command=lambda: self.go(-1), style="Compact.TButton")
        self.previous.pack(side="left")
        self.next = ttk.Button(bar, text="Próxima", command=lambda: self.go(1), style="Compact.TButton")
        self.next.pack(side="right")
        self.position = ttk.Label(bar, style="Muted.TLabel")
        self.position.pack()
        self.player = Preview(deck, preview)
        self.detail = ttk.Frame(deck, style="Card.TFrame", padding=(11, 9))
        self.title = ttk.Label(self.detail, style="Card.TLabel", font=("Segoe UI Semibold", 14),
                               wraplength=275)
        self.title.pack(anchor="w")
        self.rating = tk.Label(self.detail, padx=7, pady=2, font=("Segoe UI Semibold", 10))
        self.rating.pack(anchor="w", pady=(5, 2))
        self.description = ttk.Label(self.detail, style="CardMuted.TLabel", wraplength=275)
        self.description.pack(anchor="w", pady=(2, 7))
        actions = ttk.Frame(self.detail, style="Card.TFrame")
        actions.pack(fill="x")
        self.buttons = []
        for text, callback, style in (("Nota", explain, "Compact.TButton"),
                                      ("Abrir Studio", studio, "Compact.TButton"),
                                      ("Agendar", schedule, "Primary.TButton")):
            button = ttk.Button(actions, text=text, style=style,
                                command=lambda action=callback: self.selected and action(self.selected[0]))
            button.pack(side="right" if text == "Agendar" else "left", padx=(0, 4))
            self.buttons.append(button)
        self.set_layout()
        self.frame.after(120, self.receive)

    def set_layout(self):
        cinema = self.layout.get() == "Sala de revisão"
        if cinema:
            self.player.frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
            self.listing.grid(row=1, column=0, sticky="new", padx=(0, 12), pady=(7, 0))
            self.detail.grid(row=0, column=1, rowspan=2, sticky="new")
        else:
            self.listing.grid(row=0, column=0, rowspan=2, sticky="new", padx=(0, 12))
            self.player.frame.grid(row=0, column=1, sticky="nsew")
            self.detail.grid(row=1, column=1, rowspan=1, sticky="new", pady=(3, 0))
        self.player.set_height(260 if cinema else 248)
        self.show()

    def set_rows(self, rows):
        self.items = rows
        if self.selected:
            for index, (row, _) in enumerate(rows):
                if row["id"] == self.selected[0]["id"]:
                    self.page = index // PAGE_SIZE
                    break
        self.show()

    def go(self, step):
        self.page += step
        self.show()

    def show(self):
        pages = max(1, (len(self.items) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = min(max(0, self.page), pages - 1)
        self.position.configure(text=f"Página {self.page+1} de {pages}" if self.items else "")
        self.previous.state(["!disabled" if self.page else "disabled"])
        self.next.state(["!disabled" if self.page + 1 < pages else "disabled"])
        for widget in self.strip.winfo_children():
            widget.destroy()
        self.images = {}
        self.boxes = {}
        colors = tema.active
        current = self.selected[0]["id"] if self.selected else None
        visible = self.items[self.page*PAGE_SIZE:(self.page+1)*PAGE_SIZE]
        if not visible:
            ttk.Label(self.strip, text="Sem clipes nesta etapa.", style="Muted.TLabel",
                      padding=(10, 28)).grid(row=0, column=0, sticky="w")
        cinema = self.layout.get() == "Sala de revisão"
        for index, entry in enumerate(visible):
            row, status = entry
            box = tk.Frame(self.strip, bg=colors["paper"], highlightthickness=1,
                           highlightbackground=colors["line"], highlightcolor=colors["focus"],
                           padx=6, pady=5, cursor="hand2", takefocus=True)
            self.strip.columnconfigure(index, weight=1, uniform="clip")
            box.grid(row=0, column=index, sticky="nsew", padx=(0, 6))
            self.boxes[row["id"]] = box
            area = tk.Frame(box, height=83 if cinema else 287, bg=colors["paper"])
            area.pack(fill="x")
            area.pack_propagate(False)
            picture = tk.Label(area, bg=colors["paper"], fg=colors["muted"], text="Clipe")
            picture.pack(fill="both", expand=True)
            title = ttk.Label(box, text=row["title"], style="Card.TLabel", font=("Segoe UI Semibold", 10),
                              wraplength=142)
            title.pack(anchor="w", pady=(5, 1))
            meta = ttk.Label(box, text=status, style="CardMuted.TLabel", font=("Segoe UI", 9), wraplength=142)
            meta.pack(anchor="w")
            text, color, background = tema.score(row["weighted_score"])
            badge = tk.Label(box, text=f"{row['weighted_score']}/100 · {text}", fg=color, bg=background,
                             padx=4, font=("Segoe UI Semibold", 9))
            badge.pack(anchor="w", pady=(3, 0))
            for widget in (box, picture, title, meta, badge):
                widget.bind("<Button-1>", lambda _, value=entry, focus=box: self.choose(value, focus))
            box.bind("<Return>", lambda _, value=entry: self.choose(value))
            box.bind("<space>", lambda _, value=entry: self.choose(value))
            key = (row["path"], "strip" if cinema else "portrait")
            self.images.setdefault(key, []).append(picture)
            if key in self.cache:
                self.show_image(key, self.cache[key])
        self.choose(next((entry for entry in visible if entry[0]["id"] == current),
                         visible[0] if visible else None))

    def choose(self, entry, focus=None):
        previous = self.selected[0]["id"] if self.selected else None
        self.selected = entry
        row = entry[0] if entry else None
        current = row["id"] if row else None
        self.player.set_clip(row)
        colors = tema.active
        for key, box in self.boxes.items():
            box.configure(highlightbackground=colors["ring"] if key == current else colors["line"])
        if focus:
            focus.focus_set()
        for button in self.buttons:
            button.configure(state="normal" if row else "disabled")
        self.title.configure(text=row["title"] if row else "Nenhum clipe selecionado")
        if row:
            score = row["weighted_score"]
            text, color, background = tema.score(score)
            self.rating.configure(text=f"{score}/100 · {text}", fg=color, bg=background)
            label = f"{entry[1]} · {row['topic']}"
            note = str(row.get("reason") or "").strip().replace("_", " ")
            self.description.configure(text=label + (f"\n{note}" if note else ""))
            key = (row["path"], "player" + str(self.player.height))
            if key in self.cache:
                self.show_image(key, self.cache[key])
        else:
            self.rating.configure(text="Sem nota", fg=colors["muted"], bg=colors["paper"])
            self.description.configure(text="Selecione um clipe para ver os detalhes.")
        if self.animation is not None:
            self.frame.after_cancel(self.animation)
            self.animation = None
        if previous != current and focus and not tema.reduced_motion():
            self.detail.configure(style="CardTransition.TFrame")
            self.animation = self.frame.after(130, self.finish_selection)
        else:
            self.detail.configure(style="Card.TFrame")
        self.load_images()

    def finish_selection(self):
        self.animation = None
        self.detail.configure(style="Card.TFrame")

    def theme_changed(self):
        self.player.recolor()
        self.show()

    def load_images(self):
        if self.inflight or not self.frame.winfo_ismapped():
            return
        needed = list(self.images)
        if self.selected:
            needed.insert(0, (self.selected[0]["path"], "player" + str(self.player.height)))
        paths = [key for key in needed if key not in self.cache]
        if paths:
            self.inflight.update(paths)
            threading.Thread(target=self.decode, args=(paths,), daemon=True).start()

    def decode(self, paths):
        for key in paths:
            path, kind = key
            size = (172, 287) if kind == "portrait" else (320, 83) if kind == "strip" else (288, int(kind[6:]))
            try:
                data = thumbnail(SimpleNamespace(path=Path(path)), size=size, landscape=kind == "strip")
            except (OSError, ValueError, RuntimeError, ImportError):
                data = None
            self.result.put((key, data))

    def show_image(self, key, data):
        visible = self.images.get(key, [])
        selected = self.selected and key == (self.selected[0]["path"], "player" + str(self.player.height))
        if data and (visible or selected):
            photo = tk.PhotoImage(data=data)
            for label in visible:
                label.configure(image=photo, text="")
                label.image = photo
            if selected:
                self.player.poster(photo)

    def receive(self):
        while not self.result.empty():
            key, data = self.result.get()
            self.inflight.discard(key)
            self.cache[key] = data
            if len(self.cache) > 16:
                self.cache.popitem(last=False)
            self.show_image(key, data)
        self.load_images()
        self.frame.after(160, self.receive)
