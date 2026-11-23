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


def gameplay_detail(signals, words, start, end, offset):
    """Choose a brief closer gameplay shot where speech or motion supports it."""
    low, high = start + 2.5, end - 3.5
    for at, _, word in words:
        if low <= at <= high and re.fullmatch(r"olha|repara|repare|senha|consegui|segredo", normalized(word)):
            return at
    motion = [(row[1], offset + index * 2.) for index, row in enumerate(signals)
              if low <= offset + index * 2. <= high and row[1] >= 1.35]
    return max(motion)[1] if motion else None


def gameplay_focus(frames, width=96, height=54):
    """Estimate a conservative center from localized motion, ignoring most HUD margins."""
    import numpy as np

    size = width * height
    images = np.frombuffer(frames[:len(frames) // size * size], dtype=np.uint8)
    images = images.reshape((-1, height, width)).astype(np.int16)
    x0, x1 = width // 5, 4 * width // 5
    y0, y1 = height // 4, 9 * height // 10
    focus = [.5]
    for change in np.abs(np.diff(images, axis=0)):
        visible = change[y0:y1, x0:x1]
        active = visible >= max(16, float(np.median(visible)) + 12)
        occupancy = float(np.mean(active))
        center = .5
        if .02 <= occupancy <= .32:
            weights = active.sum(axis=0)
            center = float(np.average(np.arange(x0, x1), weights=weights)) / width
        target = min(.72, max(.28, .5 + (center - .5) * 1.25))
        focus.append(round(.6 * focus[-1] + .4 * target, 4))
    return focus


def focus_expression(samples, offset):
    if len(samples) <= 1:
        return ".5"
    time = f"(t+{max(0., offset):.3f})"
    result = f"{samples[-1]:.4f}"
    for index in range(len(samples) - 2, -1, -1):
        if index + 1 < offset:
            break
        start, end = samples[index:index + 2]
        result = (f"if(lt({time},{index + 1}),{start:.4f}+"
                  f"({end - start:.4f})*clip({time}-{index},0,1),{result})")
    return result


def gameplay_with_face(shots):
    if not shots:
        return shots
    start, end, _ = shots[0]
    if end - start >= 3.4:
        return [(start, start + 2., "split"), (start + 2., end, "gamecam"), *shots[1:]]
    if end - start >= 1.2 and len(shots) > 1:
        low, high, _ = shots[1]
        return [(start, end, "split"), (low, high, "gamecam"), *shots[2:]]
    return shots


def kit_direction(words, *, force=False):
    spoken = normalized(" ".join(word for _, _, word in words))
    mentions_gta6 = bool(GTA_SIX.search(spoken))
    if not (force or mentions_gta6):
        return None
    if re.search(r"\b(?:qual (?:e )?a senha|cade a senha|nao tem (?:essa |a )?senha)\b", spoken):
        return {"kind": "descoberta", "label": "Descoberta", "accent": "senha",
                "hook": "Cadê a senha?", "question": "Onde você procuraria a senha?",
                "mentions_gta6": mentions_gta6}
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
