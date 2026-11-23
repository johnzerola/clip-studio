"""Adapt the GTA kit's editing and post style to speech already found in a clip."""
import re
import unicodedata


GTA_SIX = re.compile(r"\b(?:gta|grand theft auto)\s+(?:6|vi|seis|six)\b", re.I)
FORMATS = (
    ("dica", "Dica de gameplay", re.compile(r"\b(?:como fazer|como usar|para conseguir|dica|tutorial|primeiro passo)\b"),
     "Que outra dica você gostaria de ver?"),
    ("reacao", "Reação", re.compile(r"\b(?:nao acredito|do nada|que susto|meu deus|olha isso)\b"),
     "Qual teria sido a sua reação?"),
    ("descoberta", "Descoberta", re.compile(r"\b(?:repara|repare|detalhe|segredo|descobri|easter egg|voce viu)\b"),
     "Que detalhe chamou mais sua atenção?"),
)


def normalized(text):
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def kit_direction(words, *, force=False):
    spoken = normalized(" ".join(word for _, _, word in words))
    mentions_gta6 = bool(GTA_SIX.search(spoken))
    if not (force or mentions_gta6):
        return None
    for key, label, pattern, question in FORMATS:
        if match := pattern.search(spoken):
            return {"kind": key, "label": label, "accent": match.group().split()[-1],
                    "question": question, "mentions_gta6": mentions_gta6}
    return {"kind": "momento", "label": "Momento de gameplay", "accent": "",
            "question": "O que mais chamou sua atenção?", "mentions_gta6": mentions_gta6}


def post_copy(direction, transcript, hook):
    # The title quotes the clip; the question adds context without inventing gameplay events.
    clean = " ".join(transcript.split())
    title = hook or " ".join(clean.split()[:8]).strip(" .,:;")
    title = title or direction["label"]
    description = " ".join(clean.split()[:22]).strip(" .,:;!?")
    if description:
        description = description[0].upper() + description[1:] + ("…" if len(clean.split()) > 22 else ".")
    else:
        description = "Trecho de gameplay da live."
    return {"title": title, "description": f"{description}\n\n{direction['question']}",
            "tags": ["#Gameplay", "#CortesDaLive", *(["#GTA6"] if direction["mentions_gta6"] else [])]}
