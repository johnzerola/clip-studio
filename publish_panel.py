"""Ready-to-publish desktop tab and explicit scheduling actions."""
import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tema
from posting_queue import STUDIOS, ranked
from publish_state import review_info, schedules, start_upload, upload_info
import youtube_publish as youtube


class PublishTab:
    def __init__(self, frame, output, review):
        self.frame = frame
        self.output = output
        self.rows = {}
        self.busy = False
        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(0, 4))
        self.count = tk.StringVar(value="Clipes aprovados")
        ttk.Label(header, textvariable=self.count, font=("Segoe UI Semibold", 12)).pack(side="left")
        ttk.Button(header, text="Revisão completa…", command=review).pack(side="right")
        self.network = tk.StringVar(value="YouTube")
        target = ttk.Combobox(header, textvariable=self.network, state="readonly", values=("YouTube","TikTok"), width=10)
        target.pack(side="right", padx=(5,10))
        ttk.Label(header,text="Nota para").pack(side="right")
        target.bind("<<ComboboxSelected>>", lambda _event:self.refresh())
        listing = ttk.Frame(frame)
        listing.pack(fill="x")
        self.table = ttk.Treeview(listing, columns=("score","title","publish"), show="headings", height=3, selectmode="browse")
        for key, name, width in (("score","Nota",85),("title","Vídeo aprovado",490),("publish","Publicação",165)):
            self.table.heading(key, text=name)
            self.table.column(key, width=width, stretch=key=="title")
        scroll = ttk.Scrollbar(listing, command=self.table.yview)
        scroll.pack(side="right",fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left",fill="x",expand=True)
        self.table.bind("<Double-1>", lambda _event: self.open())
        self.table.bind("<<TreeviewSelect>>", self.selection)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(6, 1))
        self.status = tk.StringVar()
        self.preview = ttk.Button(row, text="Assistir", command=self.open)
        self.preview.pack(side="left")
        self.why = ttk.Button(row, text="Entender a nota", command=self.explain)
        self.why.pack(side="left", padx=5)
        self.schedule = ttk.Button(row, text="Publicar ou agendar…", command=self.open_schedule,
                                   style="Primary.TButton")
        self.schedule.pack(side="right")
        ttk.Label(row, textvariable=self.status, style="Muted.TLabel").pack(side="left", padx=8)
        self.listed = None
        self.selection()
        self.tick()

    def current(self):
        ids = self.table.selection()
        return self.rows.get(ids[0]) if ids else None

    def selection(self, _event=None):
        state = ["!disabled"] if self.current() else ["disabled"]
        for button in (self.preview, self.why, self.schedule):
            button.state(state)

    def tick(self):
        if self.frame.winfo_ismapped():
            self.refresh()
        self.frame.after(3500, self.tick)

    def refresh(self):
        try:
            folder = self.output()
            rows = []
            agenda = {}
            if (folder/"postagens.sqlite3").is_file():
                rows = [row for row in ranked(folder, platform=self.network.get()) if row["result"] == "ready"
                        and row["path"] and Path(row["path"]).is_file()]
                if self.network.get() == "YouTube":
                    agenda = schedules(folder)
        except Exception:
            self.status.set("Confira a pasta de saída.")
            return
        signature = [(row["id"], row["title"], row["weighted_score"], row["path"], agenda.get(row["id"])) for row in rows]
        if signature != self.listed:
            self.listed = signature
            selected = self.table.selection()
            self.rows = {row["id"]: row for row in rows}
            self.table.delete(*self.table.get_children())
            for row in rows:
                note = str(row["weighted_score"]) + ("*" if row["weighted_score"] != row["score"] else "")
                labels = {"scheduled":"Agendado", "uploaded":"Conferir no Studio", "sending":"Enviando",
                          "uncertain":"Conferir envio", "failed":"Envio falhou"}
                label = labels.get(agenda.get(row["id"]), "Para revisar")
                self.table.insert("", "end", iid=row["id"], values=(note, row["title"], label))
            if rows:
                self.table.selection_set(selected[0] if selected and selected[0] in self.rows else rows[0]["id"])
        count = len(rows)
        self.count.set(f"{count} clipe" + (" aprovado" if count == 1 else "s aprovados"))
        self.status.set("* Nota ajustada por retenção" if any(r["weighted_score"] != r["score"] for r in rows)
                        else "Selecione um clipe para revisar" if rows else "Os clipes aprovados aparecem aqui")
        self.selection()

    def open(self):
        if self.current():
            try:
                os.startfile(self.current()["path"])
            except OSError as error:
                messagebox.showerror("Clipes prontos", str(error), parent=self.frame)

    def explain(self):
        row = self.current()
        if not row:
            return
        info = review_info(self.output(), row["id"])
        model = info.get("model") or "Regras locais"
        evidence = info.get("semantic") or {}
        cards = ", ".join(evidence.get("knowledge", []))
        text = f"Nota original {row['score']}/100\nNota na fila {row['weighted_score']}/100"
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

    def open_schedule(self):
        selected = self.current()
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

        def field(row, label, widget):
            ttk.Label(box, text=label).grid(row=row,column=0,sticky="nw",pady=4,padx=(0,10))
            widget.grid(row=row,column=1,sticky="ew",pady=4)

        selector = ttk.Combobox(box, textvariable=platform, state="readonly", values=("YouTube","TikTok"))
        field(0,"Destino",selector)
        field(1,"Título",ttk.Entry(box,textvariable=title,width=53))
        body = tk.Text(box, height=4, width=45, wrap="word")
        body.insert("1.0",(selected["description"] or "")+"\n\n"+(selected["tags"] or ""))
        field(2,"Descrição", body)
        field(3,"Horário local",ttk.Entry(box,textvariable=date))
        field(4,"Feito para crianças",ttk.Combobox(box,textvariable=audience,state="readonly",
                                                  values=("Escolher…","Sim","Não")))
        ttk.Label(box,textvariable=channel,wraplength=510).grid(row=5,columnspan=2,sticky="w",pady=(6,3))
        ttk.Label(box,textvariable=status,style="Muted.TLabel",wraplength=510).grid(row=7,columnspan=2,sticky="w",pady=(5,0))

        def load():
            try:
                data = youtube.account()
                return data.get("channel") if data else None
            except (OSError, ValueError, RuntimeError):
                return None

        def display(_event=None):
            profile=load()
            for button in (account_button,send_button,studio_button):
                button.state(["disabled"] if self.busy else ["!disabled"])
            if platform.get() == "TikTok":
                channel.set("TikTok Studio · finalize o envio e escolha a data no navegador.")
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
            def upload():
                row=start_upload(folder,selected["id"],profile["id"],when,meta,
                                 lambda line:tasks.put(("progress",line)))
                return row["detail"]+(f" ID {row['video']}" if row.get("video") else "")
            work(upload)

        buttons=ttk.Frame(box)
        buttons.grid(row=6,columnspan=2,sticky="ew",pady=(5,0))
        account_button=ttk.Button(buttons,text="Conectar YouTube…",command=connect)
        account_button.pack(side="left")
        def studio():
            window.clipboard_clear()
            window.clipboard_append(body.get("1.0","end-1c"))
            webbrowser.open(STUDIOS[platform.get()])
            status.set("Descrição copiada. Selecione o MP4 no Studio.")
        studio_button=ttk.Button(buttons,text="Abrir Studio",command=studio)
        studio_button.pack(side="left",padx=6)
        send_button=ttk.Button(buttons,text="Enviar e agendar",style="Primary.TButton",command=send)
        send_button.pack(side="right")
        selector.bind("<<ComboboxSelected>>",display)
        window.protocol("WM_DELETE_WINDOW",lambda: None if self.busy else window.destroy())
        display()
