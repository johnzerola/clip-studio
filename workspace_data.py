"""Dashboard read models shared by the native workspace and posting gallery."""
from contextlib import closing
import re

from posting_queue import db_open
from publish_state import table

TOPICS = {
    "Curiosidade": r"você sabia|sabia que|segredo|curiosidade|descobri",
    "Conversa": r"fofoca|rumor|disseram|notícia|polêmica",
    "Jogada": r"clutch|corrida|fuga|jogada|partida|matei|perseguição",
    "Reação": r"eita|reação|não acredito|meu deus|caramba|impossível",
}


def topic(text):
    return next((name for name, pattern in TOPICS.items()
                 if re.search(pattern, text, re.I)), "História")


def observed(db, platform, theme):
    rows = [(topic(f"{title} {description}"), min(150, retention))
            for title, description, retention in db.execute("""
                SELECT c.title,c.description,r.retention FROM clip_retention r
                JOIN clips c ON c.id=r.clip WHERE r.platform=? AND r.views>=100 AND c.result='ready'
            """, (platform,))]
    same = [value for name, value in rows if name == theme]
    others = [value for name, value in rows if name != theme]
    if len(same) < 3 or len(others) < 3:
        return 0
    delta = sum(same) / len(same) - sum(others) / len(others)
    return max(-5, min(5, round(delta / 4)))


def editorial_weights(folder):
    if not (folder / "postagens.sqlite3").is_file():
        return {}
    with closing(db_open(folder)) as db:
        return {theme: round(sum(observed(db, network, theme) for network in ("YouTube", "TikTok")) / 2)
                for theme in (*TOPICS, "História")}


def register_exports(folder, paths):
    paths = tuple((str(path.resolve()),) for path in paths if path.is_file())
    if paths:
        with closing(db_open(folder)) as db, db:
            db.executemany("INSERT OR IGNORE INTO clip_exports (path) VALUES (?)", paths)


def overview(folder):
    if not (folder / "postagens.sqlite3").is_file():
        return (0, 0, 0, 0), []
    with closing(db_open(folder)) as db, db:
        from studio_services import social_table
        table(db)
        social_table(db)
        counts = db.execute("""
            WITH state(clip,status) AS (
                SELECT clip,CASE status WHEN 'agendado confirmado' THEN 'scheduled'
                   WHEN 'publicado confirmado' THEN 'published' ELSE status END FROM destinations UNION
                SELECT clip,CASE status WHEN 'agendado confirmado' THEN 'scheduled'
                   WHEN 'publicado confirmado' THEN 'published' ELSE status END FROM destination_accounts UNION
                SELECT clip,state FROM uploads UNION
                SELECT clip,'scheduled' FROM studio_social WHERE state='provider_scheduled'
            )
            SELECT
                (SELECT COUNT(*) FROM (SELECT path FROM clip_exports UNION SELECT path FROM clips WHERE path IS NOT NULL)),
                COUNT(*) FILTER (WHERE result='ready' AND path IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM state WHERE clip=c.id AND status IN ('scheduled','published'))),
                COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM state WHERE clip=c.id AND status='scheduled')),
                COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM state WHERE clip=c.id AND status='published'))
            FROM clips c
        """).fetchone()
        rows = db.execute("""
            SELECT c.title,c.description,r.platform,r.views,r.retention
              FROM clip_retention r JOIN clips c ON c.id=r.clip
             WHERE r.views>0 ORDER BY r.retention DESC,r.views DESC LIMIT 5
        """).fetchall()
        return tuple(counts), [(title, topic(f"{title} {description}"), platform, views, retention)
                               for title, description, platform, views, retention in rows]
