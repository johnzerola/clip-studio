"""Diálogos visuais do painel principal."""
import base64
import os
import tkinter as tk
from tkinter import ttk

import tema
from broll_library import STILLS


def thumbnail(asset):
    import cv2
    import numpy as np

    if asset.path.suffix.lower() in STILLS:
        frame = cv2.imdecode(np.fromfile(asset.path, dtype=np.uint8), cv2.IMREAD_COLOR)
    else:
        capture = cv2.VideoCapture(str(asset.path))
        try:
            frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if frames > 6:
                capture.set(cv2.CAP_PROP_POS_FRAMES, min(45, frames // 4))
            ok, frame = capture.read()
            if not ok:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = capture.read()
            if not ok:
                return None
        finally:
            capture.release()
    if frame is None:
        return None
    height, width = frame.shape[:2]
    scale = min(340 / width, 188 / height, 1)
    frame = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))),
                       interpolation=cv2.INTER_AREA)
    ok, png = cv2.imencode(".png", frame)
    return base64.b64encode(png).decode("ascii") if ok else None


def open_library(parent, get_assets, chosen, pick_folder, on_change):
    window = tk.Toplevel(parent)
    window.title("Biblioteca de B-roll")
    window.geometry("770x475")
    window.minsize(720, 440)
    window.transient(parent)
    frame = ttk.Frame(window, padding=15)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)
    ttk.Label(frame, text="Escolha imagens e vídeos para ilustrar a fala").grid(row=0, column=0, sticky="w")
    filters = ttk.Frame(frame)
    filters.grid(row=1, column=0, columnspan=2, sticky="ew", pady=8)
    group = tk.StringVar(value="Todos")
    query = tk.StringVar()
    groups = ttk.Combobox(filters, textvariable=group, state="readonly", width=14)
    groups.pack(side="left")
    ttk.Label(filters, text="Buscar").pack(side="left", padx=(12, 5))
    ttk.Entry(filters, textvariable=query, width=25).pack(side="left")
    table_frame = ttk.Frame(frame)
    table_frame.grid(row=2, column=0, sticky="nsew")
    tree = ttk.Treeview(table_frame, columns=("use",), selectmode="browse")
    tree.heading("#0", text="Item")
    tree.heading("use", text="Usar")
    tree.column("#0", width=245)
    tree.column("use", width=54, minwidth=54, stretch=False, anchor="center")
    tree.pack(side="left", fill="both", expand=True)
    scroll = ttk.Scrollbar(table_frame, command=tree.yview)
    scroll.pack(side="right", fill="y")
    tree.configure(yscrollcommand=scroll.set)
    detail = ttk.Frame(frame, width=350)
    detail.grid(row=2, column=1, sticky="nsew", padx=(12, 0))
    detail.grid_propagate(False)
    picture = ttk.Label(detail, anchor="center")
    picture.place(x=0, y=0, width=350, height=190)
    info = ttk.Label(detail, wraplength=340)
    info.place(x=0, y=192)
    choice = tk.BooleanVar()
    checkbox = ttk.Checkbutton(detail, text="Usar automaticamente se combinar com a fala", variable=choice)
    checkbox.place(x=0, y=239)
    play = ttk.Button(detail, text="Abrir arquivo original")
    play.place(x=0, y=264)
    status = tk.StringVar()
    ttk.Label(frame, textvariable=status).grid(row=3, column=0, sticky="w", pady=(8, 0))
    ttk.Button(frame, text="Concluir", command=window.destroy, style="Primary.TButton").grid(
        row=3, column=1, sticky="e", pady=(8, 0))

    assets = {}
    current = None

    def show(_event=None):
        nonlocal current
        selection = tree.selection()
        asset = assets.get(selection[0]) if selection else None
        if asset == current and asset is not None:
            return
        current = asset
        choice.set(bool(asset and asset.key in chosen))
        checkbox.configure(state="normal" if asset else "disabled")
        play.configure(state="normal" if asset else "disabled")
        try:
            data = thumbnail(asset) if asset else None
            picture.image = tk.PhotoImage(master=window, data=data) if data else None
        except (OSError, ValueError, RuntimeError, tk.TclError):
            picture.image = None
        picture.configure(image=picture.image or "",
                          text="" if picture.image else "Prévia indisponível" if asset else "Selecione um item")
        info.configure(text=f"{asset.group} · Ativa com: {', '.join(asset.cues)}" if asset else "")

    def refresh(*_):
        previous = tree.selection()
        tree.delete(*tree.get_children())
        term = query.get().strip().casefold()
        for key, asset in assets.items():
            if group.get() in ("Todos", asset.group) and term in asset.label.casefold():
                tree.insert("", "end", iid=key, text=asset.label,
                            values=("Sim" if asset.key in chosen else "",))
        if previous and tree.exists(previous[0]):
            tree.selection_set(previous[0])
        elif tree.get_children():
            tree.selection_set(tree.get_children()[0])
        show()
        count = sum(asset.key in chosen for asset in assets.values())
        status.set("1 item selecionado" if count == 1 else f"{count} itens selecionados")

    def reload():
        assets.clear()
        assets.update((asset.key, asset) for asset in get_assets())
        groups.configure(values=["Todos", "GTA 6", "Memes", "Gatinhos", "Minha pasta"])
        refresh()

    def toggle():
        if current is None:
            return
        if choice.get():
            chosen.add(current.key)
        else:
            chosen.discard(current.key)
        on_change()
        refresh()

    def clear():
        chosen.clear()
        on_change()
        choice.set(False)
        refresh()

    checkbox.configure(command=toggle)
    play.configure(command=lambda: os.startfile(current.path) if current else None)
    ttk.Button(filters, text="Minha pasta…", command=lambda: (pick_folder(), reload())).pack(side="right")
    ttk.Button(filters, text="Desmarcar todos", command=clear).pack(side="right", padx=6)
    tree.bind("<<TreeviewSelect>>", show)
    groups.bind("<<ComboboxSelected>>", refresh)
    query.trace_add("write", refresh)
    reload()
    return window


def open_styles(parent, style, labels):
    window = tk.Toplevel(parent)
    window.title("Escolher estilo do vídeo")
    window.transient(parent)
    frame = ttk.Frame(window, padding=16)
    frame.pack()
    colors = {"face": "#89ded2", "game": "#315564"}

    def draw(canvas, layout, x):
        def facecam(left, top, right, bottom):
            canvas.create_oval(x + left, top, x + right, bottom, fill=colors["face"], width=0)

        def panel(top, bottom, kind, text):
            canvas.create_rectangle(x, top, x + 48, bottom, fill=colors[kind], width=0)
            canvas.create_text(x + 24, (top + bottom) // 2, text=text,
                               fill=tema.DEEP if kind == "face" else "white", font=("Segoe UI", 8))

        if layout == "split":
            panel(4, 34, "face", "Rosto")
            panel(34, 89, "game", "Jogo")
        elif layout == "gamecam":
            panel(4, 89, "game", "Jogo")
            facecam(29, 8, 45, 24)
        else:
            panel(4, 89, "face", "Rosto")
            if layout == "reaction":
                canvas.create_rectangle(x + 27, 8, x + 45, 24, fill=colors["game"], width=0)

    descriptions = {
        "dynamic": "Dinâmico: alterna rosto e jogo.",
        "split": "Rosto em cima, jogo embaixo.",
        "gamecam": "Jogo com webcam redonda no canto.",
        "reaction": "Rosto com jogo pequeno no canto.",
        "all": "Gera três versões do mesmo corte.",
    }

    def choose(label):
        style.set(label)
        window.destroy()

    for index, (label, layout) in enumerate(labels.items()):
        card = ttk.Frame(frame, padding=8, style="Card.TFrame")
        card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=4, pady=4)
        canvas = tk.Canvas(card, width=165, height=93, bg=tema.PAPER, highlightthickness=0)
        canvas.pack()
        if layout in {"all", "dynamic"}:
            examples = ("face", "split", "gamecam") if layout == "dynamic" else ("face", "split", "reaction")
            for offset, example in enumerate(examples):
                draw(canvas, example, offset * 55 + 3)
        else:
            draw(canvas, layout, 59)
        canvas.bind("<Button-1>", lambda _event, label=label: choose(label))
        ttk.Label(card, text=descriptions[layout], style="Card.TLabel", wraplength=170).pack(pady=4)
        ttk.Button(card, text="Selecionado" if style.get() == label else "Escolher",
                   command=lambda label=label: choose(label)).pack(fill="x")
    return window
