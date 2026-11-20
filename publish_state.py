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
