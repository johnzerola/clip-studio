"""Read-only queue view across browser drafts, YouTube and Upload-Post."""
from contextlib import closing
from datetime import datetime
import sqlite3
from tkinter import ttk

from posting_queue import db_open
from publish_state import table
from studio_services import social_table

SOCIAL = {"provider_scheduled": "Recebido pelo Upload-Post", "provider_pending": "Em processamento",
          "rejected": "Recusado", "uncertain": "Conferir envio", "sending": "Enviando"}
YOUTUBE = {"scheduled": "Agendado", "uploaded": "Conferir no Studio", "sending": "Enviando",
           "uncertain": "Conferir envio", "failed": "Falhou"}


def agenda_rows(folder):
    if not (folder / "postagens.sqlite3").is_file():
        return ()
    with closing(db_open(folder)) as db, db:
        table(db)
        social_table(db)
        entries = []
        for when, title, channel, state in db.execute("""SELECT u.when_utc,c.title,u.channel,u.state
            FROM uploads u JOIN clips c ON c.id=u.clip"""):
            entries.append((when, title, "YouTube", channel, YOUTUBE.get(state, state)))
        for when, title, platform, profile, state in db.execute("""SELECT p.planned,c.title,p.platform,p.profile,p.state
            FROM studio_social p JOIN clips c ON c.id=p.clip"""):
            entries.append((when, title, platform.title(), profile, SOCIAL.get(state, state)))
        for when, title, platform, profile, state in db.execute("""SELECT d.planned,c.title,d.platform,d.account,d.status
            FROM destination_accounts d JOIN clips c ON c.id=d.clip WHERE COALESCE(d.planned,'')!=''
            UNION SELECT d.planned,c.title,d.platform,'',d.status FROM destinations d
            JOIN clips c ON c.id=d.clip WHERE COALESCE(d.planned,'')!=''"""):
            entries.append((when, title, platform, profile, state.capitalize()))
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='browser_drafts'").fetchone():
            for when, title, platform in db.execute("""SELECT COALESCE(b.planned,''),COALESCE(NULLIF(b.title,''),c.title),b.platform
                FROM browser_drafts b JOIN clips c ON c.id=b.clip
                LEFT JOIN destinations d ON b.clip=d.clip AND b.platform=d.platform
                WHERE d.status IS NULL OR d.status IN ('rascunho confirmado','aguardando')"""):
                entries.append((when, title, platform, "", "Rascunho local"))
    result = []
    for when, title, platform, profile, status in entries:
        display = when or "Sem horário"
        timestamp = float("inf")
        if when:
            try:
                at = datetime.fromisoformat(when).astimezone() if "T" in when else datetime.strptime(when, "%d/%m/%Y %H:%M")
                display, timestamp = at.strftime("%d/%m/%Y %H:%M"), at.timestamp()
            except (ValueError, OverflowError):
                pass
        result.append((timestamp, display, title, platform, profile or "—", status))
    return tuple(item[1:] for item in sorted(set(result)))


class Agenda:
    def __init__(self, frame, output, open_posts):
        self.frame, self.output = frame, output
        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Agenda", font=("Segoe UI Semibold", 22)).pack(side="left")
        ttk.Button(header, text="Abrir Postagens", command=open_posts).pack(side="right")
        ttk.Label(frame, text="Acompanhe horários, rascunhos e envios por conta.", style="Muted.TLabel").pack(anchor="w")
        list_area = ttk.Frame(frame, style="Card.TFrame")
        list_area.pack(fill="x", pady=10)
        columns = (("when","Horário local",132),("title","Clipe",210),("target","Rede",88),
                   ("account","Conta ou perfil",118),("state","Status",154))
        self.table = ttk.Treeview(list_area, columns=[c[0] for c in columns], show="headings", height=8)
        scroll = ttk.Scrollbar(list_area, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        for key, title, width in columns:
            self.table.heading(key, text=title)
            self.table.column(key,width=width, minwidth=65, stretch=key=="title")
        self.table.pack(fill="x", expand=True)
        self.caption = ttk.Label(frame, style="Muted.TLabel")
        self.caption.pack(anchor="w")
        self.latest = None
        self.frame.after(3500, self.tick)

    def tick(self):
        if self.frame.winfo_ismapped():
            self.refresh()
        self.frame.after(3500, self.tick)

    def refresh(self):
        try:
            rows = agenda_rows(self.output())
        except (OSError, RuntimeError, ValueError, sqlite3.Error):
            self.caption.configure(text="Confira a pasta de saída selecionada.")
            return
        if rows != self.latest:
            self.latest = rows
            self.table.delete(*self.table.get_children())
            for row in rows:
                self.table.insert("", "end", values=row)
        self.caption.configure(text=f"{len(rows)} registro(s)" if rows else "Os horários que você guardar em Postagens aparecem aqui.")
