"""Ready-to-publish desktop tab and explicit scheduling actions."""
import os
import queue
import sqlite3
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tema
from clip_gallery import ClipGallery
from posting_queue import STATES, STUDIOS, disposition, ranked
from publish_state import browser_draft, browser_states, review_info, schedules, start_upload, upload_info
import youtube_publish as youtube
from studio_panel import social_dialog, thumbnail_path, ugc_dialog, youtube_studio
from studio_services import social_states


class PublishTab:
    def __init__(self, frame, output, review, model, autopilot, layout, save_preferences):
        self.frame = frame
        self.output = output
        self.busy = False
        self.filter = "Para revisar"
        self.layout = layout
        header = ttk.Frame(frame)
        header.pack(fill="x")
        self.count = tk.StringVar(value="Postagens")
        ttk.Label(header, textvariable=self.count, style="Page.TLabel", font=("Segoe UI Semibold", 22)).pack(side="left")
        ttk.Button(header, text="Fila e métricas…", command=review).pack(side="right")
        ttk.Button(header, text="Ator de IA…", command=lambda: ugc_dialog(frame, self.output)).pack(side="right", padx=6)
        self.auto_status = tk.StringVar(value="Piloto automático…")
        if autopilot:
            ttk.Button(header, textvariable=self.auto_status, command=autopilot).pack(side="right", padx=6)
        self.network = tk.StringVar(value="YouTube")
        target = ttk.Combobox(header, textvariable=self.network, state="readonly", values=tuple(STUDIOS), width=10)
        target.pack(side="right", padx=(5, 10))
        ttk.Label(header, text="Avaliar para").pack(side="right")
        target.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(8, 3))
        self.filters = {}
        for name in ("Para revisar", "Agendados", "Publicados", "Todos"):
            button = ttk.Button(toolbar, text=name, style="TabChoice.TButton",
                                command=lambda value=name: self.set_filter(value))
            button.pack(side="left", padx=(0, 4))
            self.filters[name] = button
        chooser = ttk.Combobox(toolbar, textvariable=layout, state="readonly",
                               values=("Galeria", "Sala de revisão"), width=17)
        chooser.pack(side="right")
        chooser.bind("<<ComboboxSelected>>", lambda _: self.change_layout(save_preferences))
        self.gallery = ClipGallery(frame, self.open, self.explain, self.open_schedule,
                                   lambda row: youtube_studio(frame, self.output(), row, model(), self.refresh),
                                   layout)
        self.listed = None
        self.tick()

    def set_filter(self, name):
        self.filter = name
        self.gallery.page = 0
        self.refresh()

    def change_layout(self, save):
        self.gallery.set_layout()
        save()

    @staticmethod
    def category(status):
        if status in ("Agendado", "Na fila social"):
            return "Agendados"
        if status == "Publicado":
            return "Publicados"
        return "Para revisar"

    def show_autopilot(self, config):
        self.auto_status.set("Piloto ligado" if config else "Piloto automático…")

    def tick(self):
        if self.frame.winfo_ismapped():
            self.refresh()
        self.frame.after(4500, self.tick)

    def refresh(self):
        try:
            folder = self.output()
            platform = self.network.get()
            rows = []
            if (folder / "postagens.sqlite3").is_file():
                states = browser_states(folder, platform)
                states.update({key: value for key, value in social_states(folder, platform).items()
                               if states.get(key) not in ("publicado confirmado", "agendado confirmado")})
                if platform == "YouTube":
                    official = schedules(folder)
                    states.update({key: value for key, value in official.items()
                                   if states.get(key) != "publicado confirmado"})
                labels = {"scheduled": "Agendado", "uploaded": "No Studio", "sending": "Enviando",
                          "uncertain": "Conferir", "provider_scheduled": "Na fila social", "provider_pending": "Em processamento",
                          "rejected": "Recusado", "failed": "Falhou", "agendado confirmado": "Agendado",
                          "publicado confirmado": "Publicado", "rascunho confirmado": "No Studio",
                          "aguardando": "Para revisar"}
                rows = [(row, labels.get(states.get(row["id"]), states.get(row["id"], "Para revisar")))
                        for row in ranked(folder, platform=platform) if row["result"] == "ready"
                        and row["path"] and Path(row["path"]).is_file()]
        except (OSError, ValueError, sqlite3.Error):
            self.count.set("Confira a pasta de saída")
            return
        for key, button in self.filters.items():
            amount = len(rows) if key == "Todos" else sum(self.category(status) == key for _, status in rows)
            button.configure(text=f"{key} ({amount})", style="TabSelected.TButton" if key == self.filter else "TabChoice.TButton")
        visible = rows if self.filter == "Todos" else [(row, state) for row, state in rows if self.category(state) == self.filter]
        signature = (platform, self.filter, [(r["id"], r["title"], r["description"], r["tags"], r["weighted_score"], r["path"], state)
                                for r, state in visible])
        if signature != self.listed:
            self.listed = signature
            self.gallery.set_rows(visible)
        self.count.set("Postagens")

    def open(self, row):
        if row:
            try:
                os.startfile(row["path"])
            except OSError as error:
                messagebox.showerror("Clipes prontos", str(error), parent=self.frame)

    def explain(self, row):
        info = review_info(self.output(), row["id"])
        model = info.get("model") or "Regras locais"
        evidence = info.get("semantic") or {}
        cards = ", ".join(evidence.get("knowledge", []))
        text = f"Nota original {row['score']}/100\nNota na fila {row['weighted_score']}/100"
        text += f"\nTema identificado: {row['topic']} · ajuste por retenção do tema: {row['topic_points']:+d}"
        if info:
            text += f"\nCaminho de avaliação {info.get('review_path', 'técnico')}\nAvaliador {model}"
            if evidence:
                metrics = (("Gancho","hook"),("Contexto","context"),("Progressão","progression"),("Desfecho","payoff"))
                text += "\n" + " · ".join(f"{label} {evidence.get(key, 0)}/4" for label,key in metrics)
            if info.get("vision_model"):
                text += f"\nAmostras de imagem {info['vision_model']}"
            if cards:
                text += f"\nCritérios consultados {cards}"
        messagebox.showinfo("Potencial do clipe", text, parent=self.frame)

    def open_schedule(self, selected):
        if not selected or self.busy:
            return
        window = tk.Toplevel(self.frame)
        window.title("Publicar ou agendar")
        window.transient(self.frame.winfo_toplevel())
        window.grab_set()
        box = ttk.Frame(window, padding=16)
        box.pack(fill="both", expand=True)
        box.columnconfigure(1, weight=1)
        platform = tk.StringVar(value=self.network.get())
        title = tk.StringVar(value=selected["title"])
        date = tk.StringVar(value=(datetime.now()+timedelta(hours=1)).strftime("%d/%m/%Y %H:%M"))
        audience = tk.StringVar(value="Escolher…")
        channel = tk.StringVar()
        status = tk.StringVar()
        tasks = queue.SimpleQueue()
        folder = self.output()
        confirmation = tk.StringVar()
        default_caption = (selected["description"] or "") + "\n\n" + (selected["tags"] or "")

        def field(row, label, widget):
            ttk.Label(box, text=label).grid(row=row,column=0,sticky="nw",pady=4,padx=(0,10))
            widget.grid(row=row,column=1,sticky="ew",pady=4)

        selector = ttk.Combobox(box, textvariable=platform, state="readonly", values=tuple(STUDIOS))
        field(0,"Destino",selector)
        field(1,"Título",ttk.Entry(box,textvariable=title,width=53))
        body = tk.Text(box, height=4, width=45, wrap="word", bg=tema.PAPER, fg=tema.INK, insertbackground=tema.INK)
        body.insert("1.0", default_caption)
        field(2,"Descrição", body)
        field(3,"Horário local",ttk.Entry(box,textvariable=date))
        kids = ttk.Combobox(box, textvariable=audience, state="readonly", values=("Escolher…","Sim","Não"))
        field(4, "Feito para crianças", kids)
        ttk.Label(box,textvariable=channel,wraplength=510).grid(row=5,columnspan=2,sticky="w",pady=(6,3))
        ttk.Label(box,textvariable=status,style="Muted.TLabel",wraplength=510).grid(row=7,columnspan=2,sticky="w",pady=(5,0))

        def load():
            try:
                data = youtube.account()
                return data.get("channel") if data else None
            except (OSError, ValueError, RuntimeError):
                return None

        def display(_event=None):
            is_youtube = platform.get() == "YouTube"
            profile = load() if is_youtube else None
            kids.configure(state="readonly" if is_youtube else "disabled")
            for button in (account_button,send_button,studio_button):
                button.state(["disabled"] if self.busy else ["!disabled"])
            if platform.get() != "YouTube":
                channel.set(f"{platform.get()} · finalize o agendamento no navegador com a conta aberta.")
                send_button.state(["disabled"])
                account_button.state(["disabled"])
                return
            channel.set(f"YouTube · {profile['title']} ({profile['id']})" if profile else "YouTube · conecte um canal")
            if not profile:
                send_button.state(["disabled"])
            else:
                saved=upload_info(folder,selected["id"],profile["id"])
                if saved and saved["state"] != "failed":
                    send_button.state(["disabled"])
                    if not self.busy:
                        status.set(saved["detail"] or "Envio em andamento ou interrompido. Confira no Studio.")

        def work(callback):
            if self.busy:
                return
            self.busy=True
            display()

            def run():
                try:
                    tasks.put(("result",callback()))
                except Exception as error:
                    tasks.put(("error",str(error) if isinstance(error,(ValueError,RuntimeError)) else
                               "Falha de autorização ou conexão. Confira a configuração e tente novamente."))
            threading.Thread(target=run,daemon=True).start()

            def poll():
                while not tasks.empty():
                    kind,text=tasks.get()
                    if kind == "progress":
                        status.set(text)
                        continue
                    self.busy=False
                    display()
                    status.set(text)
                    self.refresh()
                    return
                window.after(160,poll)
            poll()

        def connect():
            path=filedialog.askopenfilename(parent=window,title="Selecionar cliente OAuth da Google",
                                            filetypes=[("Cliente OAuth para computador","*.json")])
            if path:
                status.set("Conclua a autorização no navegador.")
                work(lambda:"Canal conectado · "+youtube.connect(path)["title"])

        def send():
            profile=load()
            if not profile:
                return
            try:
                when=youtube.future_time(date.get().strip())
                if audience.get() not in ("Sim","Não") or not title.get().strip():
                    raise ValueError("Preencha o título e escolha se o vídeo foi feito para crianças.")
                meta={"title":title.get().strip(),"description":body.get("1.0","end-1c"),"kids":audience.get()=="Sim"}
            except ValueError as error:
                status.set(str(error))
                return
            if not messagebox.askyesno("Confirmar envio","Enviar este clipe ao canal "
                                      +profile["title"]+" para publicação em "+date.get()+" (horário local)?",parent=window):
                return
            cover = thumbnail_path(folder, selected["id"])
            if cover.is_file():
                meta["thumbnail"] = str(cover)
            def upload():
                row=start_upload(folder,selected["id"],profile["id"],when,meta,
                                 lambda line:tasks.put(("progress",line)))
                return row["detail"]+(f" ID {row['video']}" if row.get("video") else "")
            work(upload)

        buttons=ttk.Frame(box)
        buttons.grid(row=6,columnspan=2,sticky="ew",pady=(5,0))
        account_button=ttk.Button(buttons,text="Conectar YouTube…",command=connect)
        account_button.pack(side="left")
        def draft():
            when = date.get().strip()
            try:
                if when:
                    datetime.strptime(when, "%d/%m/%Y %H:%M")
            except ValueError:
                status.set("Use DD/MM/AAAA HH:MM para o horário local.")
                return False
            browser_draft(folder, selected["id"], platform.get(),
                          {"title": title.get().strip(), "caption": body.get("1.0", "end-1c"), "planned": when})
            self.refresh()
            return True

        def copy(text):
            window.clipboard_clear()
            window.clipboard_append(text)

        def studio():
            if draft():
                copy(body.get("1.0", "end-1c"))
                webbrowser.open(STUDIOS[platform.get()])
                status.set("Descrição copiada. Selecione o MP4 no site e confirme a data por lá.")

        def confirm():
            if confirmation.get() in STATES[1:] and draft():
                disposition(folder, selected["id"], platform.get(), confirmation.get(), date.get().strip())
                self.refresh()
                status.set("Confirmação registrada neste computador.")

        def change_destination(_event=None):
            saved = browser_draft(folder, selected["id"], platform.get())
            state, planned = disposition(folder, selected["id"], platform.get())
            title.set(saved.get("title", selected["title"]))
            date.set(saved.get("planned") or planned or (datetime.now()+timedelta(hours=1)).strftime("%d/%m/%Y %H:%M"))
            body.delete("1.0", "end")
            body.insert("1.0", saved.get("caption", default_caption))
            confirmation.set(state)
            display()

        studio_button=ttk.Button(buttons,text="Abrir no navegador",command=studio)
        studio_button.pack(side="left",padx=6)
        actions=ttk.Frame(box)
        actions.grid(row=8,columnspan=2,sticky="ew",pady=(8,0))
        ttk.Button(actions, text="Guardar rascunho local",
                   command=lambda: draft() and status.set("Rascunho guardado para este destino.")).pack(side="left")
        ttk.Button(actions, text="Copiar caminho do MP4", command=lambda: copy(selected["path"])).pack(side="left", padx=6)
        ttk.Button(actions, text="Copiar título", command=lambda: copy(title.get())).pack(side="left")
        ttk.Button(actions, text="Agendar via Upload-Post…",
                   command=lambda: social_dialog(window, folder, selected, platform.get(), title.get(),
                                                 body.get("1.0", "end-1c"), date.get(), self.refresh)).pack(side="left", padx=6)
        confirm_row=ttk.Frame(box)
        confirm_row.grid(row=9,columnspan=2,sticky="ew",pady=(8,0))
        ttk.Combobox(confirm_row, textvariable=confirmation, values=STATES, state="readonly",
                     width=24).pack(side="left")
        ttk.Button(confirm_row, text="Registrar o que confirmei no site", command=confirm).pack(side="left", padx=6)
        send_button=ttk.Button(buttons,text="Enviar e agendar",style="Primary.TButton",command=send)
        send_button.pack(side="right")
        selector.bind("<<ComboboxSelected>>",change_destination)
        window.protocol("WM_DELETE_WINDOW",lambda: None if self.busy else window.destroy())
        change_destination()
