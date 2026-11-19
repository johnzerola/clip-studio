"""Local clip score history with optional observed retention."""
import argparse
import json
import sqlite3
from pathlib import Path

SCHEMA = """CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP, raw_score INTEGER,
    score INTEGER, chat_messages INTEGER, model TEXT, accepted INTEGER, output TEXT,
    retention REAL, views INTEGER
)"""


def record(database, key, decision, output=None):
    with sqlite3.connect(database) as db:
        db.execute(SCHEMA)
        db.execute("""INSERT INTO decisions(id,raw_score,score,chat_messages,model,accepted,output)
                      VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET output=excluded.output""",
                   (key, decision["raw_score"], decision["score"], decision["chat_messages"],
                    decision["model"], decision["accepted"], output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--id")
    parser.add_argument("--retention", type=float, help="Porcentagem observada; pode passar de 100 em loops.")
    parser.add_argument("--views", type=int)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Banco não encontrado.")
    if args.retention is not None and (not args.id or not 0 <= args.retention <= 1000):
        parser.error("Informe um ID e retenção válida.")
    if args.views is not None and (not args.id or args.views < 0):
        parser.error("Informe um ID e visualizações válidas.")
    with sqlite3.connect(args.database) as db:
        db.row_factory = sqlite3.Row
        if args.retention is not None or args.views is not None:
            updated = db.execute("""UPDATE decisions SET retention=COALESCE(?,retention),
                                    views=COALESCE(?,views) WHERE id=? AND accepted=1""",
                                 (args.retention, args.views, args.id))
            if not updated.rowcount:
                parser.error("ID aprovado não encontrado.")
        rows = db.execute("SELECT * FROM decisions ORDER BY created DESC LIMIT 100")
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
