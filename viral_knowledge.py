"""Small offline retrieval index of editorial criteria, authored for Clip Studio."""
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "knowledge" / "viralidade.json"
LOCAL = ROOT / "criterios.local.json"


def terms(text):
    value = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
    return set(re.findall(r"\b[a-z0-9]{3,}\b", value))


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
    return [{"id":row["id"][:40], "rule":row["rule"][:215]} for row in matches[:limit]]
