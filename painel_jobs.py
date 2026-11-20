"""Display the jobs submitted from any Clip Studio entry point."""
import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from job_registry import ACTIVE, cancel, get, list_jobs

LABELS = {"queued": "Na fila", "running": "Em andamento", "completed": "Concluído",
          "failed": "Falhou", "cancelled": "Cancelado", "interrupted": "Interrompido"}


def open_jobs(parent):
    window = tk.Toplevel(parent)
    window.title("Trabalhos do Clip Studio")
    window.geometry("860x540")
    window.minsize(630, 440)
    frame = ttk.Frame(window, padding=15)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Trabalhos do painel, CLI e MCP", font=("Segoe UI Semibold", 15)).pack(anchor="w")
    table = ttk.Treeview(frame, columns=("id","origin","state","output"), show="headings", height=7)
    for key, label, width in (("id","ID",85),("origin","Origem",75),("state","Estado",125),("output","Pasta de saída",420)):
        table.heading(key, text=label)
        table.column(key, width=width, stretch=key == "output")
    table.pack(fill="x", pady=(10, 6))
    log = tk.Text(frame, height=8, wrap="word", state="disabled")
    log.pack(fill="both", expand=True)
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(8, 0))
    rows = {}
    last_listing = None
    last_detail = None
    timer = None

    def selected():
        keys = table.selection()
        return rows.get(keys[0]) if keys else None

    def show(_event=None):
        nonlocal last_detail
        row = selected()
        detail = get(row["id"], limit=500) if row else {}
        events = detail.get("events", [])
        lines = ([row["session"] or row["output"], row.get("detail") or ""]
                 + [item["line"] for item in events]) if row else ["Nenhum trabalho registrado."]
        signature = (row["id"] if row else None, tuple(lines))
        if signature != last_detail:
            last_detail = signature
            log.configure(state="normal")
            log.delete("1.0", "end")
            log.insert("end", "\n".join(line for line in lines if line))
            log.see("end")
            log.configure(state="disabled")
        stop_button.state(["!disabled"] if row and row["state"] in ACTIVE and not row["cancel"] else ["disabled"])
        folder_button.state(["!disabled"] if row and Path(row["session"] or row["output"]).is_dir() else ["disabled"])

    def refresh():
        nonlocal last_listing, timer
        listing = list_jobs(50)
        marker = [(row["id"], row["state"], row["cancel"], row["session"], row["detail"]) for row in listing]
        if marker != last_listing:
            last_listing = marker
            current = table.selection()
            table.delete(*table.get_children())
            rows.clear()
            for row in listing:
                key = row["id"]
                rows[key] = row
                state = "Parando" if row["cancel"] and row["state"] in ACTIVE else LABELS[row["state"]]
                table.insert("", "end", iid=key, values=(key[:8], row["origin"], state, row["output"]))
            if rows:
                table.selection_set(current[0] if current and current[0] in rows else next(iter(rows)))
        show()
        timer = window.after(1250, refresh)

    def open_folder():
        row = selected()
        if row:
            try:
                os.startfile(row["session"] or row["output"])
            except OSError as error:
                messagebox.showerror("Pasta indisponível", str(error), parent=window)

    def stop_work():
        row = selected()
        if row:
            cancel(row["id"])
            stop_button.state(["disabled"])

    folder_button = ttk.Button(buttons, text="Abrir pasta do trabalho", command=open_folder)
    folder_button.pack(side="left")
    stop_button = ttk.Button(buttons, text="Pedir parada", command=stop_work)
    stop_button.pack(side="left", padx=8)
    table.bind("<<TreeviewSelect>>", show)
    window.bind("<Destroy>", lambda event: window.after_cancel(timer) if event.widget is window and timer else None)
    refresh()
    return window
