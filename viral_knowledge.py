"""Small offline retrieval index of editorial criteria, authored for Clip Studio."""
import json
import math
import re
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "knowledge" / "viralidade.json"
LOCAL = ROOT / "criterios.local.json"
_history = ()
COMMON = set("ainda agora algum assim com como coisa dela dele dos essa esse esta este foi isso mais mas muito não nao nos para pela pelo por porque pode quando que sem ser suas tava tem ter todo tudo uma voce".split())


def terms(text):
    value = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
    return set(re.findall(r"\b[a-z0-9]{3,}\b", value)) - COMMON


def load_history(folder):
    """Load a small working set of observed results from the current workspace."""
    global _history
    _history = ()
    database = Path(folder).resolve() / "postagens.sqlite3"
    if not database.is_file():
        return
    try:
        from clip_quality import MIN_VIEWS
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            rows = db.execute("""SELECT c.title, c.description, c.score, r.platform, r.retention, r.views, f.vote, r.updated
                FROM clips c JOIN clip_retention r ON r.clip=c.id
                LEFT JOIN editorial_feedback f ON f.clip=c.id AND f.platform=r.platform
                WHERE c.result='ready' AND r.views>=?
                UNION ALL
                SELECT c.title, c.description, c.score, f.platform, NULL, NULL, f.vote, c.updated
                FROM clips c JOIN editorial_feedback f ON f.clip=c.id
                WHERE NOT EXISTS (SELECT 1 FROM clip_retention r WHERE r.clip=c.id AND r.platform=f.platform AND r.views>=?)
                ORDER BY 8 DESC LIMIT 100""", (MIN_VIEWS, MIN_VIEWS)).fetchall()
        _history = tuple((terms((title or "") + " " + (description or "")[:360]), {
            "id": f"resultado-local-{i + 1}", "source": "historico_local", "title": (title or "")[:85],
            "network": platform, "vote": vote, "prior_score": score,
            **({"retention": round(retention, 1), "views": views} if retention is not None else {})})
            for i, (title, description, score, platform, retention, views, vote, _) in enumerate(rows))
    except (sqlite3.Error, ValueError):
        return


def read_cards(path):
    try:
        if path.stat().st_size > 100_000:
            return []
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    return [row for row in rows[:100] if isinstance(row, dict)
            and all(isinstance(row.get(key), str) for key in ("id","tags","rule"))]


def retrieve(transcript, evidence, limit=3):
    cards = {row["id"]: row for path in (BASE, LOCAL) for row in read_cards(path)}
    query = terms(transcript[:2000] + " " + " ".join(key for key, value in evidence.items() if value))
    terms_by_card = {key: terms(card["tags"]) for key, card in cards.items()}
    weights = {term: math.log1p(len(cards) / (1 + sum(term in tags for tags in terms_by_card.values())))
               for term in query if any(term in tags for tags in terms_by_card.values())}
    matches = [row for row in cards.values() if terms_by_card[row["id"]] & weights.keys()]
    matches.sort(key=lambda row: -sum(weights[term] for term in terms_by_card[row["id"]] & weights.keys()))
    if "arco" in cards and cards["arco"] not in matches:
        matches.insert(0, cards["arco"])
    selected = [{"id": row["id"][:40], "rule": row["rule"][:215],
                 **({"source": row["source"][:220]} if isinstance(row.get("source"), str) else {})}
                for row in matches[:limit]]
    historical = [(len(query & tokens), item) for tokens, item in _history if len(query & tokens) >= 3]
    historical.sort(key=lambda row: -row[0])
    return selected + [item for _, item in historical[:2]]
