"""Scheduling status kept separate from the editorial and retention scores."""
from contextlib import closing
import hashlib
import json
from pathlib import Path

from posting_queue import db_open


def table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS uploads (
        clip TEXT NOT NULL, channel TEXT NOT NULL, when_utc TEXT NOT NULL,
        state TEXT NOT NULL, video TEXT, detail TEXT, PRIMARY KEY (clip,channel)
    )""")


def upload_info(folder, clip, channel):
    with closing(db_open(folder)) as db, db:
        table(db)
        row = db.execute("SELECT * FROM uploads WHERE clip=? AND channel=?", (clip, channel)).fetchone()
        return dict(row) if row else None


def start_upload(folder, clip, channel, when, meta, progress):
    from datetime import datetime
    from youtube_publish import UploadUncertain, send

    with closing(db_open(folder)) as db, db:
        table(db)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT path,title,description,tags FROM clips WHERE id=? AND result='ready'",
                         (clip,)).fetchone()
        if not row or not row["path"]:
            raise ValueError("Escolha um clipe aprovado com arquivo disponível.")
        previous = db.execute("SELECT state FROM uploads WHERE clip=? AND channel=?", (clip, channel)).fetchone()
        if previous and previous[0] != "failed":
            raise ValueError("Já há um envio ou registro para este canal. Confira o status antes de repetir.")
        db.execute("""INSERT INTO uploads VALUES (?,?,?,'sending',NULL,NULL)
                      ON CONFLICT(clip,channel) DO UPDATE SET
                      when_utc=excluded.when_utc,state='sending',video=NULL,detail=NULL""",
                   (clip, channel, when))
    video = None
    try:
        path = Path(row["path"])
        if path.suffix.lower() != ".mp4":
            raise ValueError("O arquivo aprovado precisa ser MP4.")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != clip:
                raise ValueError("O arquivo mudou desde a aprovação. Avalie o MP4 novamente.")
        progress("Enviando ao YouTube")
        result = send(path, meta, when, channel, progress)
        video = result["id"]
        confirmed = result.get("status", {}).get("publishAt")
        scheduled = confirmed and datetime.fromisoformat(confirmed) == datetime.fromisoformat(when)
        status = "scheduled" if scheduled else "uploaded"
        detail = ("Agendamento confirmado pelo YouTube." if scheduled else
                  "Upload recebido. Confirme no Studio o horário e a visibilidade.")
        if result.get("thumbnail_warning"):
            detail += " " + result["thumbnail_warning"]
    except UploadUncertain as error:
        status, detail = "uncertain", str(error)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        status, detail = "failed", (str(error) if isinstance(error, (ValueError, RuntimeError))
                                    else "Falha ao verificar arquivo ou conexão do YouTube.")
    with closing(db_open(folder)) as db, db:
        table(db)
        db.execute("UPDATE uploads SET state=?,video=?,detail=? WHERE clip=? AND channel=?",
                   (status, video, detail, clip, channel))
    return upload_info(folder, clip, channel)


def browser_draft(folder, clip, platform, data=None):
    with closing(db_open(folder)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS browser_drafts (
            clip TEXT NOT NULL, platform TEXT NOT NULL, title TEXT, caption TEXT, planned TEXT,
            PRIMARY KEY(clip,platform))""")
        if data is not None:
            db.execute("""INSERT OR REPLACE INTO browser_drafts VALUES (?,?,?,?,?)""",
                       (clip, platform, data["title"], data["caption"], data["planned"]))
        row = db.execute("SELECT title,caption,planned FROM browser_drafts WHERE clip=? AND platform=?",
                         (clip, platform)).fetchone()
        return dict(row) if row else {}


def browser_states(folder, platform):
    with closing(db_open(folder)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS browser_drafts (
            clip TEXT NOT NULL, platform TEXT NOT NULL, title TEXT, caption TEXT, planned TEXT,
            PRIMARY KEY(clip,platform))""")
        return {row["clip"]: row["status"] for row in db.execute("""
            SELECT b.clip,COALESCE(d.status,'Rascunho local') AS status
              FROM browser_drafts b LEFT JOIN destinations d ON d.clip=b.clip AND d.platform=b.platform
             WHERE b.platform=?
            UNION ALL
            SELECT d.clip,d.status FROM destinations d
             WHERE d.platform=? AND NOT EXISTS (
                SELECT 1 FROM browser_drafts b WHERE b.clip=d.clip AND b.platform=d.platform
             )
        """, (platform, platform))}


def review_info(folder, clip):
    with closing(db_open(folder)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS clip_reviews (clip TEXT PRIMARY KEY, detail TEXT NOT NULL)")
        row = db.execute("SELECT detail FROM clip_reviews WHERE clip=?", (clip,)).fetchone()
        return json.loads(row[0]) if row else {}

def schedules(folder):
    with closing(db_open(folder)) as db, db:
        table(db)
        values = db.execute("SELECT clip,state FROM uploads ORDER BY when_utc DESC").fetchall()
        latest = {}
        for clip, state in values:
            latest.setdefault(clip, state)
        return latest
