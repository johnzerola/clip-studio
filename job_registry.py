"""Small local job registry shared by the panel, CLI and the MCP server."""
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "work" / "jobs.sqlite3"
ACTIVE = ("queued", "running")
TERMINAL = ("completed", "failed", "cancelled", "interrupted")


@contextmanager
def connect():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DATABASE, timeout=8)) as db:
        db.row_factory = sqlite3.Row
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, origin TEXT NOT NULL, state TEXT NOT NULL, output TEXT NOT NULL,
                session TEXT, sources TEXT NOT NULL, request TEXT, created REAL NOT NULL,
                updated REAL NOT NULL, cancel INTEGER NOT NULL DEFAULT 0, detail TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, line TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS event_job ON events(job,seq)")
            db.execute("""CREATE TABLE IF NOT EXISTS source_activity (
                job TEXT NOT NULL, source TEXT NOT NULL, state TEXT NOT NULL,
                PRIMARY KEY(job,source))""")
            yield db


def expire(db):
    db.execute("""UPDATE jobs SET state='interrupted', detail='Processo sem resposta', updated=?
                  WHERE state IN ('queued','running') AND updated<?""", (time.time(), time.time()-120))


def reserve(origin, sources, output, request=None):
    key = uuid4().hex
    now = time.time()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire(db)
        current = db.execute("SELECT id FROM jobs WHERE state IN ('queued','running')").fetchone()
        if current:
            raise RuntimeError(f"Já existe um trabalho ativo ({current['id'][:8]}).")
        db.execute("""INSERT INTO jobs (id,origin,state,output,sources,request,created,updated)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (key, origin, "queued", str(output), json.dumps(sources, ensure_ascii=False),
                    json.dumps(request, ensure_ascii=False) if request else None, now, now))
        # Keep the registry bounded without touching any result or media.
        old = """SELECT id FROM jobs WHERE state NOT IN ('queued','running') ORDER BY created DESC LIMIT -1 OFFSET 100"""
        db.execute(f"DELETE FROM events WHERE job IN ({old})")
        db.execute(f"DELETE FROM source_activity WHERE job IN ({old})")
        db.execute(f"DELETE FROM jobs WHERE id IN ({old})")
    return key


def get(key, *, after=0, limit=0):
    with connect() as db:
        expire(db)
        row = db.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone()
        if row is None:
            raise ValueError("Trabalho não encontrado.")
        out = {k: row[k] for k in row.keys() if k != "request"}
        out["sources"] = json.loads(out["sources"])
        if limit:
            out["events"] = [dict(item) for item in db.execute(
                "SELECT seq,line FROM events WHERE job=? AND seq>? ORDER BY seq LIMIT ?",
                (key, max(0, after), min(500, max(1, limit))))]
        return out


def active_sources(output):
    with connect() as db:
        expire(db)
        return [tuple(row) for row in db.execute("""
            SELECT a.source,a.state FROM source_activity a JOIN jobs j ON j.id=a.job
            WHERE j.state='running' AND j.output=? ORDER BY a.source
        """, (str(output),))]


def list_jobs(limit=25):
    with connect() as db:
        expire(db)
        return [dict(row) for row in db.execute(
            """SELECT id,origin,state,output,session,created,updated,cancel,detail
               FROM jobs ORDER BY created DESC LIMIT ?""", (min(100, max(1, limit)),))]


def job_activity(key):
    with connect() as db:
        return [tuple(row) for row in db.execute(
            "SELECT source,state FROM source_activity WHERE job=? ORDER BY source", (key,))]


def cancel(key):
    with connect() as db:
        expire(db)
        if not db.execute("SELECT 1 FROM jobs WHERE id=?", (key,)).fetchone():
            raise ValueError("Trabalho não encontrado.")
        db.execute("""UPDATE jobs SET cancel=1, state='cancelled', request=NULL, updated=?
                      WHERE id=? AND state='queued'""", (time.time(), key))
        db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND state='running'", (key,))
    return get(key)


def finish(key, status, detail=None):
    with connect() as db:
        db.execute("UPDATE jobs SET state=?,detail=?,request=NULL,updated=? WHERE id=? AND state IN ('queued','running')",
                   (status, detail, time.time(), key))


def start(key, action, stop, log):
    done = threading.Event()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT state,cancel FROM jobs WHERE id=?", (key,)).fetchone()
        if row is None or row["state"] != "queued":
            raise RuntimeError("Esse trabalho não está na fila.")
        db.execute("UPDATE jobs SET state='running',updated=? WHERE id=?", (time.time(), key))
        if row["cancel"]:
            stop.set()

    def heartbeat():
        next_write = time.monotonic() + 10
        while not done.wait(1):
            try:
                with connect() as db:
                    row = db.execute("SELECT cancel FROM jobs WHERE id=?", (key,)).fetchone()
                    if row and row["cancel"]:
                        stop.set()
                    now = time.monotonic()
                    if now >= next_write:
                        db.execute("UPDATE jobs SET updated=? WHERE id=? AND state='running'", (time.time(), key))
                        next_write = now + 10
            except sqlite3.Error:
                continue

    def event(line):
        log(line)
        with connect() as db:
            db.execute("INSERT INTO events(job,line) VALUES(?,?)", (key, str(line)[:2000]))
            db.execute("""DELETE FROM events WHERE job=? AND seq<
                          COALESCE((SELECT seq FROM events WHERE job=? ORDER BY seq DESC LIMIT 1 OFFSET 499),0)""",
                       (key, key))

    def session(path):
        with connect() as db:
            db.execute("UPDATE jobs SET session=? WHERE id=?", (str(path), key))

    worker = threading.Thread(target=heartbeat, daemon=True)
    worker.start()
    try:
        code = 0 if stop.is_set() else action(event, session)
        finish(key, "cancelled" if stop.is_set() else "failed" if code else "completed",
               "Consulte o registro para detalhes." if code else None)
        return code or 0
    except BaseException as error:
        finish(key, "cancelled" if stop.is_set() else "failed", str(error)[:500])
        raise
    finally:
        done.set()
        worker.join()


def tracked_session(origin, sources, options, minutes, workers, output, wait_minutes, stop, log, scout, key=None):
    from sessions import run_session

    key = key or reserve(origin, [value for value, _, _ in sources], output)

    def activity(source, state):
        with connect() as db:
            db.execute("INSERT OR REPLACE INTO source_activity VALUES (?,?,?)", (key, source, state))

    def action(event, session):
        return run_session(sources, options, minutes, workers, output, wait_minutes, stop, event, scout,
                           on_batch=session, activity=activity)

    return start(key, action, stop, log)


def submit(request, origin):
    # Keep the MCP process responsive while the worker imports video libraries.
    raw = request.get("sources")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 8 or any(
            not isinstance(value, str) or not value.strip() for value in raw):
        raise ValueError("Informe de 1 a 8 fontes não vazias.")
    values = []
    for value in raw:
        value = value.strip()
        path = Path(value)
        values.append(str(path.resolve()) if "://" not in value and path.is_file() else value)
    output = Path(request.get("output") or ROOT / "resultados").resolve()
    if output.exists() and not output.is_dir():
        raise ValueError("A saída precisa ser uma pasta.")
    request = dict(request, sources=values, output=str(output))
    key = reserve(origin, values, output, request)
    try:
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        if os.name == "nt" and request.get("performance", "leve") == "leve":
            flags |= subprocess.BELOW_NORMAL_PRIORITY_CLASS
        subprocess.Popen([sys.executable, "-X", "utf8", str(ROOT / "jobs_cli.py"), "_run", key],
                         cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags, start_new_session=os.name != "nt")
    except OSError as error:
        finish(key, "failed", str(error))
        raise
    return get(key)


def request_for(key):
    with connect() as db:
        row = db.execute("SELECT request FROM jobs WHERE id=? AND state='queued'", (key,)).fetchone()
    if not row or not row["request"]:
        raise ValueError("Trabalho sem pedido pendente.")
    return json.loads(row["request"])


def outputs(key, *, row=None):
    row = row if row is not None else get(key)
    if not row["session"]:
        return {"id": key, "session": None, "clips": [], "plans": [], "transcripts": []}
    folder = Path(row["session"]).resolve()
    if not folder.is_relative_to(Path(row["output"]).resolve()) or not folder.is_dir():
        return {"id": key, "session": None, "clips": [], "plans": [], "transcripts": []}
    clips = folder / "Clipes prontos"
    return {"id": key, "session": str(folder), "clips": [str(path) for path in sorted(clips.rglob("clip_*.mp4"))
                                                       if path.is_file() and path.resolve().is_relative_to(folder)],
            "plans": [str(path) for path in sorted(clips.rglob("cortes.json"))],
            "transcripts": [str(path) for path in sorted(clips.rglob("transcricao.txt"))]}
