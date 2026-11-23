"""Local clip score history with optional observed retention."""
import argparse
from contextlib import closing
import json
import sqlite3
from pathlib import Path

SCHEMA = """CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP, raw_score INTEGER,
    score INTEGER, chat_messages INTEGER, model TEXT, accepted INTEGER, output TEXT,
    retention REAL, views INTEGER
)"""


FEEDBACK = """CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY REFERENCES decisions(id), label TEXT NOT NULL, note TEXT NOT NULL
)"""


FINAL = """CREATE TABLE IF NOT EXISTS final_reviews (
    id TEXT NOT NULL, variant TEXT NOT NULL, score INTEGER NOT NULL, status TEXT NOT NULL,
    detail TEXT NOT NULL, PRIMARY KEY (id, variant)
)"""


def record_final(database, key, variants):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(FINAL)
        db.executemany("""INSERT INTO final_reviews VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id, variant) DO UPDATE SET score=excluded.score, status=excluded.status,
            detail=excluded.detail""",
            [(key, style, review["score"], review["status"], json.dumps(review, ensure_ascii=False))
             for style, review in variants])
        if any(style == "fila" and review["status"] == "skipped" for style, review in variants):
            db.execute(SCHEMA)
            db.execute("UPDATE decisions SET output=NULL WHERE id=?", (key,))


def calibration(db):
    """Aggregate editorial labels and observed retention separately."""
    db.execute(FEEDBACK)
    db.execute(FINAL)
    buckets = db.execute("""SELECT COALESCE(r.final_score, d.score) / 10 * 10 AS score_floor, COUNT(f.label) AS reviewed,
        SUM(CASE WHEN f.label='bom' THEN 1 ELSE 0 END) AS good,
        COUNT(d.retention) AS retention_samples, ROUND(AVG(d.retention), 1) AS avg_retention
        FROM decisions d LEFT JOIN feedback f USING(id)
        LEFT JOIN (SELECT id, MAX(score) AS final_score FROM final_reviews WHERE variant <> 'fila' GROUP BY id) r USING(id)
        GROUP BY score_floor ORDER BY score_floor""")
    return [dict(row) for row in buckets]


def record(database, key, decision, output=None):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(SCHEMA)
        db.execute(FINAL)
        db.execute("""INSERT INTO decisions(id,raw_score,score,chat_messages,model,accepted,output)
                      VALUES(?,?,?,?,?,?,CASE WHEN EXISTS(
                          SELECT 1 FROM final_reviews WHERE id=? AND variant='fila' AND status='skipped'
                      ) THEN NULL ELSE ? END) ON CONFLICT(id) DO UPDATE SET output=excluded.output""",
                   (key, decision["raw_score"], decision["score"], decision["chat_messages"],
                    decision["model"], decision["accepted"], key, output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--id")
    parser.add_argument("--label", choices=("bom", "fraco"), help="Avaliação editorial humana.")
    parser.add_argument("--note", default="", help="Por que este corte funcionou ou falhou.")
    parser.add_argument("--calibration", action="store_true", help="Resumo por faixa de nota.")
    parser.add_argument("--retention", type=float, help="Porcentagem observada; pode passar de 100 em loops.")
    parser.add_argument("--views", type=int)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Banco não encontrado.")
    if args.retention is not None and (not args.id or not 0 <= args.retention <= 1000):
        parser.error("Informe um ID e retenção válida.")
    if args.views is not None and (not args.id or args.views < 0):
        parser.error("Informe um ID e visualizações válidas.")
    if args.label and not args.id:
        parser.error("Informe o ID da decisão que você revisou.")
    with sqlite3.connect(args.database) as db:
        db.row_factory = sqlite3.Row
        db.execute(FINAL)
        if args.retention is not None or args.views is not None:
            updated = db.execute("""UPDATE decisions SET retention=COALESCE(?,retention),
                                    views=COALESCE(?,views) WHERE id=? AND accepted=1
                                    AND (NOT EXISTS (SELECT 1 FROM final_reviews r WHERE r.id=decisions.id)
                                         OR EXISTS (SELECT 1 FROM final_reviews r WHERE r.id=decisions.id AND r.status='ready'))""",
                                 (args.retention, args.views, args.id))
            if not updated.rowcount:
                parser.error("ID aprovado não encontrado.")
        db.execute(FEEDBACK)
        if args.label:
            if not db.execute("SELECT 1 FROM decisions WHERE id=?", (args.id,)).fetchone():
                parser.error("ID não encontrado.")
            db.execute("""INSERT INTO feedback VALUES (?, ?, ?) ON CONFLICT(id)
                       DO UPDATE SET label=excluded.label, note=excluded.note""",
                       (args.id, args.label, args.note[:1000]))
        if args.calibration:
            print(json.dumps(calibration(db), ensure_ascii=False, indent=2))
            return
        rows = db.execute("""SELECT d.*, f.label AS editorial_label, f.note AS editorial_note
                             , (SELECT MAX(score) FROM final_reviews r WHERE r.id=d.id) AS final_score
                             , (SELECT GROUP_CONCAT(status) FROM final_reviews r WHERE r.id=d.id) AS final_status
                             FROM decisions d LEFT JOIN feedback f USING(id)
                             ORDER BY d.created DESC LIMIT 100""")
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
