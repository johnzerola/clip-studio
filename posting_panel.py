"""Tk review queue for final clips, metadata, and handoff to native web studios."""
import json
import os
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tema
from runtime_profile import lower_worker_priority
from posting_queue import (STUDIOS, STATES, calibration_count, disposition, enqueue,
                           index_previous, ranked, retention)


def show_queue(parent, folder, model, threshold):
    window = tk.Toplevel(parent)
    window.title("Fila de postagem")
    window.geometry("960x610")
    window.minsize(850, 560)
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    heading = ttk.Frame(frame, padding=(12, 8), style="Card.TFrame")
    heading.grid(row=0, column=0, sticky="ew")
    ttk.Label(heading, text="Revisão e publicação", style="Heading.TLabel").pack(anchor="w")
    ttk.Label(heading, text="Escolha os melhores cortes, confira a nota e acompanhe a retenção.",
              style="Card.TLabel").pack(side="left")
    hide_similar = tk.BooleanVar(value=False)
    ttk.Checkbutton(heading, text="Ocultar parecidos", variable=hide_similar,
                    command=lambda: refresh()).pack(side="right")
    table = ttk.Treeview(frame, columns=("score", "status", "title"), show="headings", height=8)
    for key, label, width in (("score", "Nota", 75), ("status", "Revisão", 125), ("title", "Título", 620)):
        table.heading(key, text=label)
        table.column(key, width=width, stretch=key == "title")
    table.tag_configure("top", background=tema.active["good_bg"], foreground=tema.active["good"])
    table.tag_configure("similar", foreground=tema.active["mid"])
    table.grid(row=1, column=0, sticky="nsew", pady=8)
    detail = tk.Text(frame, height=7, wrap="word", state="disabled")
    detail.grid(row=2, column=0, sticky="ew")
    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, sticky="w", pady=8)
    import_actions = ttk.Frame(frame)
    import_actions.grid(row=4, column=0, sticky="w", pady=(0, 8))
    status = ttk.Frame(frame)
    status.grid(row=5, column=0, sticky="ew")
    platform = tk.StringVar(value="YouTube")
    state = tk.StringVar(value=STATES[0])
    account = tk.StringVar()
    planned = tk.StringVar()
    progress = tk.StringVar()
    rows = {}
    closed = threading.Event()
    window.bind("<Destroy>", lambda event: closed.set() if event.widget is window else None)

    def current():
        selection = table.selection()
        return rows.get(selection[0]) if selection else None

    def show(_event=None):
        row = current()
        if not row:
            state.set(STATES[0])
            planned.set("")
        else:
            saved, date = disposition(folder, row["id"], platform.get(), account=account.get())
            state.set(saved)
            planned.set(date or "")
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        if row:
            measured, views = retention(folder, row["id"], platform.get())
            detail.insert("end", f"{row['score']}/100 original · {row['weighted_score']}/100 na fila de {platform.get()}\n")
            if measured is not None:
                detail.insert("end", f"{measured:.1f}% assistido · {views:,} visualizações\n")
            if row["similar_title"] and row["similar_path"] and Path(row["similar_path"]).is_file():
                detail.insert("end", f"Parecido com “{row['similar_title']}”\n")
            trends = ", ".join(f"{t['source']}: {t['topic']}" for t in json.loads(row["trends"]))
            detail.insert("end", f"{row['title']}\n\n{row['description']}\n{row['tags']}\n"
                          f"Tendências cruzadas: {trends or 'nenhuma correspondência'}\n"
                          f"{row['reason'] or ''}")
        detail.configure(state="disabled")

    def refresh():
        selected = table.selection()
        table.delete(*table.get_children())
        rows.clear()
        top = set()
        for row in ranked(folder, platform=platform.get()):
            similar = bool(row["duplicate_of"] and row["similar_path"] and Path(row["similar_path"]).is_file())
            if similar and hide_similar.get():
                continue
            rows[row["id"]] = row
            approved = row["result"] == "ready"
            path = Path(row["path"]) if row["path"] else None
            group = (path.parent, path.stem.removesuffix("_dynamic").removesuffix("_split")
                     .removesuffix("_reaction")) if path else None
            highlight = approved and not similar and path and path.is_file() and group not in top and len(top) < 3
            if highlight:
                top.add(group)
            score = str(row["weighted_score"]) + ("*" if row["weighted_score"] != row["score"] else "")
            review = "Parecido" if similar else "Aprovado" if approved else "Descartado"
            table.insert("", "end", iid=row["id"], values=(score, review, row["title"]),
                         tags=("top",) if highlight else ("similar",) if similar else ())
        if selected and selected[0] in rows:
            table.selection_set(selected[0])
        elif rows:
            table.selection_set(next(iter(rows)))
        show()

    def copy(field):
        row = current()
        if not row or not row["path"]:
            return
        value = f"{row['description']}\n\n{row['tags']}" if field == "copy" else row[field]
        window.clipboard_clear()
        window.clipboard_append(value)
        progress.set("Copiado.")

    def open_media():
        row = current()
        if row and row["path"]:
            try:
                os.startfile(row["path"])
            except OSError as error:
                messagebox.showerror("Arquivo", str(error), parent=window)

    def save():
        row = current()
        if not row or not row["path"]:
            return
        date = planned.get().strip()
        if date:
            try:
                datetime.strptime(date, "%d/%m/%Y %H:%M")
            except ValueError:
                messagebox.showerror("Data de publicação", "Use DD/MM/AAAA HH:MM.", parent=window)
                return
        disposition(folder, row["id"], platform.get(), state.get(), date, account=account.get())
        progress.set("Status local registrado. O agendamento é feito no Studio.")

    def record_retention():
        row = current()
        if not row or row["result"] != "ready":
            progress.set("Selecione um clipe aprovado.")
            return
        destination = platform.get()
        seen, count = retention(folder, row["id"], destination)
        dialog = tk.Toplevel(window)
        dialog.title(f"Retenção · {destination}")
        dialog.transient(window)
        box = ttk.Frame(dialog, padding=16)
        box.pack()
        percentage = tk.StringVar(value="" if seen is None else str(seen))
        views = tk.StringVar(value="" if count is None else str(count))
        ttk.Label(box, text="Use a porcentagem média assistida no painel do canal.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        for index, (name, value) in enumerate((("Porcentagem assistida", percentage), ("Visualizações", views)), 1):
            ttk.Label(box, text=name).grid(row=index, column=0, sticky="w", pady=4)
            ttk.Entry(box, textvariable=value, width=15).grid(row=index, column=1, sticky="e", padx=(12, 0))
        remark = tk.StringVar(value="A nota da fila usa amostras por plataforma a partir de 100 visualizações.")
        ttk.Label(box, textvariable=remark, style="Muted.TLabel", wraplength=400).grid(row=3, columnspan=2, sticky="w")

        def submit():
            try:
                retention(folder, row["id"], destination, float(percentage.get().strip().rstrip("%").replace(",", ".")),
                          int(views.get().strip().replace(".", "").replace(" ", "")))
                samples = calibration_count(folder, destination)
            except (ValueError, OSError) as error:
                remark.set(str(error))
                return
            dialog.destroy()
            refresh()
            sample_label = "1 clipe" if samples == 1 else f"{samples} clipes"
            progress.set(f"Retenção registrada. {sample_label} com amostra suficiente em {destination}.")

        ttk.Button(box, text="Salvar retenção", style="Primary.TButton", command=submit).grid(
            row=4, column=1, sticky="e", pady=(8, 0))
        dialog.bind("<Return>", lambda _event: submit())

    def trends_editor():
        dialog = tk.Toplevel(window)
        dialog.title("Tendências para cruzar com a fala")
        path = folder / "tendencias.json"
        try:
            content = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(content, dict):
                content = {}
        except (OSError, ValueError):
            content = {}
        fields = {}
        for name, title, link in (
            ("youtube", "Google Trends · pesquisa no YouTube",
             "https://trends.google.com/trends/explore?geo=BR&gprop=youtube"),
            ("tiktok", "TikTok Creative Center",
             "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"),
        ):
            ttk.Button(dialog, text=title, command=lambda url=link: webbrowser.open(url)).pack(anchor="w", padx=12, pady=4)
            box = tk.Text(dialog, height=5, width=60)
            box.pack(padx=12)
            terms = content.get(name, [])
            if isinstance(terms, list):
                box.insert("1.0", "\n".join(term for term in terms if isinstance(term, str)))
            fields[name] = box
        ttk.Label(dialog, text="Cole um termo por linha. As sugestões entram quando combinam com a fala.").pack(padx=12, pady=5)

        def persist():
            values = {key: [line.strip() for line in box.get("1.0", "end").splitlines() if line.strip()][:200]
                      for key, box in fields.items()}
            try:
                draft = path.with_suffix(".tmp")
                draft.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
                draft.replace(path)
            except OSError as error:
                messagebox.showerror("Tendências", str(error), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(dialog, text="Guardar termos", command=persist).pack(anchor="e", padx=12, pady=8)

    def run_index():
        from queue import SimpleQueue

        events = SimpleQueue()
        old_button.state(["disabled"])

        def run():
            try:
                count = index_previous(folder, events.put, stop=closed)
                events.put((f"{count} clipes antigos verificados." if count
                            else "Nenhum clipe antigo disponível para verificar.",))
            except Exception as error:
                events.put((str(error),))

        def poll_index():
            while not events.empty():
                event = events.get_nowait()
                if isinstance(event, tuple):
                    progress.set(event[0])
                    refresh()
                    old_button.state(["!disabled"])
                    return
                progress.set(event)
            window.after(200, poll_index)

        threading.Thread(target=run, daemon=True).start()
        window.after(200, poll_index)

    def analyze_existing():
        files = filedialog.askopenfilenames(parent=window, title="Escolher MP4s finalizados",
                                            filetypes=[("Vídeos MP4", "*.mp4")])
        if not files:
            return
        import_button.state(["disabled"])
        from queue import Queue
        events = Queue()

        def analyze():
            lower_worker_priority()
            from engine import FF, command, probe, transcribe
            from final_screen import evaluate
            for value in files:
                try:
                    path = Path(value)
                    duration, audio = probe(path)
                    if duration > 180:
                        raise ValueError("Escolha clipes de até 180 segundos.")
                    words = transcribe(path, 0, duration) if audio else []
                    verdict = evaluate(path, FF, command, duration, words, model, threshold, {})
                    verdict["duration"] = duration
                    enqueue(folder, path, path if verdict["status"] == "ready" else None, verdict,
                            " ".join(w for _, _, w in words), "", model)
                    events.put(f"{path.name}: {verdict['score']}/100")
                except Exception as error:
                    events.put(str(error))
            events.put(None)

        def poll():
            while not events.empty():
                item = events.get_nowait()
                if item is None:
                    refresh()
                    import_button.state(["!disabled"])
                    return
                progress.set(item)
            window.after(250, poll)

        threading.Thread(target=analyze, daemon=True).start()
        window.after(250, poll)

    for label, action in (("Atualizar", refresh), ("Ver clipe", open_media), ("Copiar título", lambda: copy("title")),
                          ("Copiar descrição", lambda: copy("copy")), ("Copiar caminho", lambda: copy("path")),
                          ("Abrir Studio", lambda: webbrowser.open(STUDIOS[platform.get()]))):
        ttk.Button(buttons, text=label, command=action).pack(side="left", padx=(0, 5))
    import_button = ttk.Button(import_actions, text="Avaliar MP4s", command=analyze_existing)
    import_button.pack(side="left")
    ttk.Button(import_actions, text="Registrar retenção…", command=record_retention).pack(side="left", padx=5)
    old_button = ttk.Button(import_actions, text="Verificar clipes antigos", command=run_index)
    old_button.pack(side="left", padx=5)
    ttk.Button(import_actions, text="Tendências", command=trends_editor).pack(side="left", padx=5)
    ttk.Label(import_actions, text="* Nota ajustada", style="Muted.TLabel").pack(side="left", padx=8)
    selector = ttk.Combobox(status, values=list(STUDIOS), textvariable=platform, state="readonly", width=10)
    selector.pack(side="left")
    selector.bind("<<ComboboxSelected>>", lambda _event: refresh())
    ttk.Label(status, text="Canal/@").pack(side="left", padx=(5, 2))
    account_entry = ttk.Entry(status, textvariable=account, width=14)
    account_entry.pack(side="left")
    account_entry.bind("<Return>", show)
    account_entry.bind("<FocusOut>", show)
    ttk.Combobox(status, values=STATES, textvariable=state, state="readonly", width=22).pack(side="left", padx=6)
    ttk.Label(status, text="Data prevista").pack(side="left")
    ttk.Entry(status, textvariable=planned, width=19).pack(side="left", padx=6)
    ttk.Button(status, text="Registrar status", command=save).pack(side="left")
    ttk.Label(frame, textvariable=progress, wraplength=880).grid(row=6, column=0, sticky="w", pady=8)
    table.bind("<<TreeviewSelect>>", show)
    refresh()
