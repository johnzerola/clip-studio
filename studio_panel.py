"""Native editing surfaces for YouTube metadata, UGC and social scheduling."""
from contextlib import closing
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from creative_studio import propose, thumbnail
from posting_queue import db_open
from studio_services import PLATFORMS, send_social, start_ugc, ugc_status


class Work:
    def __init__(self, window, status):
        self.window = window
        self.status = status
        self.pending = False

    def run(self, action, callback):
        if self.pending:
            return
        self.pending = True
        self.status.set("Processando…")
        result = queue.SimpleQueue()

        def execute():
            try:
                result.put((True, action()))
            except Exception as error:
                result.put((False, str(error) if isinstance(error, (RuntimeError, ValueError)) else
                            "Não foi possível concluir a operação."))

        def poll():
            if result.empty():
                self.window.after(160, poll)
                return
            self.pending = False
            ok, value = result.get()
            if ok:
                callback(value)
            else:
                self.status.set(value)

        threading.Thread(target=execute, daemon=True).start()
        poll()


def window_for(parent, title):
    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent.winfo_toplevel())
    box = ttk.Frame(window, padding=16)
    box.pack(fill="both", expand=True)
    box.columnconfigure(1, weight=1)
    ttk.Label(box, text=title, font=("Segoe UI Semibold", 19)).grid(row=0, columnspan=2, sticky="w", pady=(0, 13))
    status = tk.StringVar(window)
    ttk.Label(box, textvariable=status, wraplength=520).grid(row=24, columnspan=2, sticky="w", pady=(10, 0))
    return window, box, status


def field(box, row, label, default="", hidden=False):
    variable = tk.StringVar(box, value=default)
    ttk.Label(box, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 9), pady=4)
    entry = ttk.Entry(box, textvariable=variable, width=48, show="•" if hidden else "")
    entry.grid(row=row, column=1, sticky="ew", pady=4)
    return variable


def thumbnail_path(folder, clip):
    import re
    if not re.fullmatch(r"[a-f0-9]{64}", clip):
        raise ValueError("Identificador de clipe inválido.")
    return folder / ".studio-thumbnails" / f"{clip}.jpg"


def youtube_studio(parent, folder, clip, model, refresh):
    window, box, status = window_for(parent, "YouTube Studio")
    tasks = Work(window, status)
    title = field(box, 1, "Título", clip["title"])
    caption = field(box, 2, "Descrição", clip["description"] or "")
    cover = field(box, 3, "Texto da miniatura", clip["title"][:42])
    at = field(box, 4, "Quadro (segundos)", "1")
    picks = ttk.Combobox(box, state="readonly", width=53)
    picks.grid(row=6, columnspan=2, sticky="ew", pady=5)
    picks.bind("<<ComboboxSelected>>", lambda _: title.set(picks.get()))

    def offer():
        from publish_state import review_info
        text = review_info(folder, clip["id"]).get("studio_transcript") or clip["description"] or clip["title"]
        hint = title.get()
        def ready(result):
            picks.configure(values=result["titles"])
            picks.current(0)
            status.set("Escolha um título na lista e salve quando estiver pronto.")
        tasks.run(lambda: propose(model, text, hint), ready)

    image_label = ttk.Label(box)
    image_label.grid(row=10, columnspan=2, pady=8, sticky="w")
    destination = thumbnail_path(folder, clip["id"])

    def show(_value=None):
        import io
        from PIL import Image
        import base64
        if destination.is_file():
            with Image.open(destination) as picture:
                picture.thumbnail((384, 216))
                buffer = io.BytesIO()
                picture.save(buffer, format="PNG")
            image = tk.PhotoImage(data=base64.b64encode(buffer.getvalue()))
            image_label.configure(image=image)
            image_label.image = image
            status.set("Miniatura JPG salva junto dos resultados.")

    def generate():
        try:
            seconds = float(at.get().replace(",", "."))
            if not 0 <= seconds < 7200 or not cover.get().strip():
                raise ValueError()
        except ValueError:
            status.set("Informe o texto e um tempo válido dentro do vídeo.")
            return
        text = cover.get()[:100]
        destination.parent.mkdir(parents=True, exist_ok=True)
        tasks.run(lambda: thumbnail(clip["path"], destination, text, seconds), show)

    def save():
        if not title.get().strip():
            status.set("Preencha o título.")
            return
        with closing(db_open(folder)) as db, db:
            db.execute("UPDATE clips SET title=?,description=? WHERE id=?",
                       (title.get().strip()[:95], caption.get().strip()[:450], clip["id"]))
        refresh()
        status.set("Título e descrição salvos no clipe.")

    bar = ttk.Frame(box)
    bar.grid(row=8, columnspan=2, sticky="w", pady=5)
    for text, command in (("Sugerir títulos", offer), ("Gerar miniatura", generate), ("Salvar no clipe", save)):
        ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 6))
    show()


def social_dialog(parent, folder, clip, network, base_title, base_caption, when, refresh):
    window, box, status = window_for(parent, "Agendamento social")
    tasks = Work(window, status)
    target = tk.StringVar(box, value=network.lower() if network.lower() in PLATFORMS else "tiktok")
    ttk.Label(box, text="Destino").grid(row=1, column=0, sticky="w")
    ttk.Combobox(box, textvariable=target, state="readonly", values=PLATFORMS).grid(row=1, column=1, sticky="ew")
    profile = field(box, 2, "Perfil Upload-Post", os.getenv("CLIP_STUDIO_SOCIAL_PROFILE", ""))
    key = field(box, 3, "Chave Upload-Post", os.getenv("CLIP_STUDIO_SOCIAL_KEY", ""), hidden=True)
    title = field(box, 4, "Título", base_title)
    caption = field(box, 5, "Legenda", base_caption)
    date = field(box, 6, "Data e hora local", when)
    ttk.Label(box, text="Deixe o horário vazio para enviar para publicação imediata.",
              style="Muted.TLabel").grid(row=7, columnspan=2, sticky="w")

    def send():
        from youtube_publish import future_time
        try:
            planned = future_time(date.get()) if date.get().strip() else None
        except ValueError as error:
            status.set(str(error))
            return
        values = target.get(), title.get(), caption.get(), planned, profile.get(), key.get()
        if not messagebox.askyesno("Confirmar envio social",
                                   f"Enviar este vídeo ao perfil {values[4]} para {values[0]}? "
                                   + (f"Horário local: {date.get()}." if planned else "Pode publicar agora."),
                                   parent=window):
            return

        def done(info):
            status.set(info)
            refresh()
        tasks.run(lambda: send_social(folder, clip["id"], *values), done)
    ttk.Button(box, text="Confirmar envio", command=send, style="Primary.TButton").grid(row=9, column=1, sticky="e")


def ugc_dialog(parent, output):
    window, box, status = window_for(parent, "Criar vídeo com ator de IA")
    tasks = Work(window, status)
    title = field(box, 1, "Título")
    actor = field(box, 2, "Descrição do ator fictício")
    ttk.Label(box, text="Roteiro falado").grid(row=3, column=0, sticky="nw", pady=5)
    script = tk.Text(box, width=48, height=5, wrap="word")
    script.grid(row=3, column=1, sticky="ew", pady=5)
    port = field(box, 4, "Porta OpenShorts", "8000")
    fal = field(box, 5, "Chave fal.ai", hidden=True)
    voice = field(box, 6, "Chave ElevenLabs", hidden=True)
    voice_id = field(box, 7, "ID da voz (opcional)")
    mode = tk.StringVar(box, value="lowcost")
    ttk.Label(box, text="Modo").grid(row=8, column=0, sticky="w")
    ttk.Combobox(box, textvariable=mode, values=("lowcost", "premium"), state="readonly").grid(row=8, column=1, sticky="ew")
    tracked = field(box, 9, "ID do trabalho")
    ttk.Label(box, text="Geração usa serviços externos pagos vinculados ao seu servidor local.",
              style="Muted.TLabel", wraplength=480).grid(row=10, columnspan=2, sticky="w")

    def generate():
        if tasks.pending or not messagebox.askyesno("Gerar vídeo com IA",
                "Enviar o roteiro para geração por fal.ai e ElevenLabs? A conta pode ser cobrada.", parent=window):
            return
        args = (port.get(), title.get(), script.get("1.0", "end-1c"), actor.get(),
                mode.get(), fal.get(), voice.get(), voice_id.get())

        def started(job):
            tracked.set(job)
            check()
        tasks.run(lambda: start_ugc(*args), started)

    def save_video():
        from tkinter import filedialog
        from studio_services import download_ugc

        destination = filedialog.asksaveasfilename(parent=window, initialdir=str(output()),
                                                  initialfile="Ator-IA.mp4", defaultextension=".mp4",
                                                  filetypes=[("Vídeo MP4", "*.mp4")])
        if destination:
            values = port.get(), tracked.get(), Path(destination)
            tasks.run(lambda: download_ugc(*values), lambda path: status.set(f"Vídeo salvo em {path}"))

    def check():
        try:
            args = port.get(), tracked.get().strip()
            from uuid import UUID
            UUID(args[1])
        except ValueError:
            status.set("Informe um ID de trabalho válido.")
            return

        def done(reply):
            state = reply.get("status")
            if reply.get("preview") and state == "completed":
                preview.configure(command=lambda: webbrowser.open(reply["preview"]), state="normal")
                save_button.configure(state="normal")
                status.set("Vídeo concluído. Confira a prévia e salve o MP4 para usar no app.")
            elif state in ("processing", "queued", "running"):
                status.set("Geração em andamento…")
                window.after(5000, check)
            else:
                status.set("Geração encerrada. Confira o trabalho no servidor.")
        tasks.run(lambda: ugc_status(*args), done)

    row = ttk.Frame(box)
    row.grid(row=12, columnspan=2, sticky="w", pady=8)
    ttk.Button(row, text="Gerar vídeo", command=generate, style="Primary.TButton").pack(side="left")
    ttk.Button(row, text="Verificar ID", command=check).pack(side="left", padx=8)
    preview = ttk.Button(row, text="Abrir vídeo", state="disabled")
    preview.pack(side="left")
    save_button = ttk.Button(row, text="Salvar MP4…", command=save_video, state="disabled")
    save_button.pack(side="left", padx=8)


def autopilot_dialog(parent, current, apply):
    from datetime import datetime
    from studio_services import Autopilot

    window, box, status = window_for(parent, "Piloto automático")
    target = tk.StringVar(box, value=current.platform if current else "youtube")
    ttk.Label(box, text="Destino").grid(row=1, column=0, sticky="w")
    ttk.Combobox(box, textvariable=target, state="readonly", values=PLATFORMS).grid(row=1, column=1, sticky="ew")
    profile = field(box, 2, "Perfil Upload-Post", current.profile if current else os.getenv("CLIP_STUDIO_SOCIAL_PROFILE", ""))
    key = field(box, 3, "Chave Upload-Post", current.key if current else os.getenv("CLIP_STUDIO_SOCIAL_KEY", ""), hidden=True)
    hour = field(box, 4, "Horário local (HH:MM)", current.hour if current else "18:00")
    minimum = field(box, 5, "Nota mínima", str(current.minimum) if current else "82")
    ttk.Label(box, text="Agenda um clipe novo por dia. Ative também a revisão dos clipes prontos em Lives e gravações.",
              style="Muted.TLabel", wraplength=480).grid(row=6, columnspan=2, sticky="w", pady=6)

    def enable():
        try:
            time = datetime.strptime(hour.get().strip(), "%H:%M").strftime("%H:%M")
            limit = int(minimum.get())
            if not 0 <= limit <= 100 or not profile.get().strip() or not key.get().strip():
                raise ValueError()
        except ValueError:
            status.set("Preencha perfil, chave, horário e nota entre 0 e 100.")
            return
        config = Autopilot(target.get(), time, limit, profile.get().strip(), key.get().strip())
        if messagebox.askyesno("Autorizar próximas publicações",
                               f"Agendar automaticamente os próximos clipes aprovados na rede {config.platform}, "
                               f"perfil {config.profile}, às {time} e com nota de pelo menos {limit}? "
                               "O Upload-Post fará as publicações nas datas aprovadas.", parent=window):
            apply(config)
            window.destroy()

    row = ttk.Frame(box)
    row.grid(row=7, columnspan=2, sticky="w", pady=8)
    ttk.Button(row, text="Ativar piloto", command=enable, style="Primary.TButton").pack(side="left")
    def disable():
        apply(None)
        window.destroy()
    ttk.Button(row, text="Desativar", command=disable).pack(side="left", padx=6)
