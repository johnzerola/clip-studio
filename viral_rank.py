"""Select timestamped live moments from speech and audiovisual evidence."""
import json
import re
import statistics
import threading
import time
import urllib.request
from runtime_profile import ollama_resources
import runtime_profile as runtime
from viral_knowledge import retrieve
from ollama_connection import active_endpoint, forget_endpoint

OLLAMA = threading.Lock()
_retry_after = {}
DIMENSIONS = {"g": "hook", "c": "context", "p": "progression", "d": "payoff"}
REASONS = ("gancho", "historia", "reacao", "repeticao", "sem_contexto", "sem_desfecho")
VISUAL_REASONS = ("imagem_pouco_nitida", "enquadramento_confuso", "legenda_ilegivel")
REACTION = re.compile(r"\b(eita|nossa|caramba|meu deus|consegui|impossível|wow|no way|clutch)\b", re.I)
CONNECTOR = re.compile(r"\b(mas|porque|então|só que|quando|de repente|finally|then|but|because)\b", re.I)
CHAT_REACTION = re.compile(
    r"\b(kekw|lul|lmao|k{4,}|pog(?:gers|champ)?|omegalul|clip(?: it)?|wtf|nossa|caraca|meu deus|ha(?:ha){2,}|monkas|sheesh)\b|😂|🔥|💀|😱",
    re.I,
)


def has_chat_reaction(message):
    return bool(CHAT_REACTION.search(message))


def candidates(words, signals, duration, limit, latest_start):
    """Use phrase edges for speech and recent peaks as anchors for silent action."""
    if duration < 8:
        return []
    ends = {duration}
    for index, (start, end, token) in enumerate(words):
        gap = words[index + 1][0] - end if index + 1 < len(words) else duration - end
        if end >= latest_start and (token.endswith((".", "!", "?")) or gap >= .65):
            ends.add(min(duration, end + .32))
    for start, audio, motion in signals:
        if start >= latest_start - 2 and (audio >= 5 or motion >= 1.8):
            ends.add(min(duration, start + 4))
    ranked = []
    target_duration = min(limit, max(16, limit * .75))
    phrases = [max(0., words[0][0] - .22)] if words else []
    for previous, current in zip(words, words[1:]):
        if previous[2].endswith((".", "!", "?")) or current[0] - previous[1] >= .65:
            phrases.append(max(0., current[0] - .22))
    for end in sorted(ends):
        low = max(0., end - limit)
        starts = [p for p in phrases if low <= p <= end - 8]
        start = min(starts, key=lambda p: abs(p - max(low, end - target_duration))) if starts else low
        spoken = [token for a, b, token in words if start <= (a + b) / 2 < end]
        transcript = " ".join(spoken)
        tokens = re.findall(r"\w+", transcript.casefold())
        unique = len(set(tokens)) / max(1, len(tokens))
        speech = min(1., len(tokens) / 20) * min(1., unique / .5)
        motion_values = [motion for at, _, motion in signals if start <= at < end]
        audio_values = [audio for at, audio, _ in signals if start <= at < end]
        movement = max(motion_values, default=0.)
        loudness = max(audio_values, default=0.)
        quiet = sum(audio < 1.8 and motion < .80
                    for audio, motion in zip(audio_values, motion_values)) / max(1, len(motion_values))
        active = sum(audio >= 4 or motion >= 1.45
                     for audio, motion in zip(audio_values, motion_values)) / max(1, len(motion_values))
        early = " ".join(spoken[:8])
        ends_cleanly = bool(spoken and spoken[-1].endswith((".", "?", "!")))
        features = {
            "speech": round(speech, 3), "quiet_fraction": round(quiet, 3), "active_fraction": round(active, 3), "reaction": bool(REACTION.search(transcript)),
            "story_link": bool(CONNECTOR.search(transcript)),
            "opening": bool(REACTION.search(early) or "?" in early),
            "audio_db": round(loudness, 2), "motion": round(movement, 2),
            "phrase_ending": ends_cleanly,
            "motion_median": round(statistics.median(motion_values), 2) if motion_values else 0.,
        }
        raw = (14 + 28 * speech + 9 * features["reaction"] + 9 * features["story_link"]
               + 6 * features["opening"] + min(14, max(0., movement - 1) * 5)
               + min(10, max(0., loudness - 2) * 1.2) + 12 * active - 18 * quiet + 4 * ends_cleanly)
        action_candidate = movement >= 2.2 and active >= .25 and quiet <= .65
        if speech < .25 and action_candidate:
            raw = max(raw, 27 + min(24, movement * 6) + 14 * active - 12 * quiet)
        if not action_candidate and (len(tokens) < 6 or unique < .42):
            raw = min(32, raw)
        ranked.append({"start": round(float(start), 3), "end": round(float(end), 3),
                       "transcript": transcript, "features": features, "av_score": max(0, min(100, round(raw)))})
    return ranked


def chat_bonus(count, ratio, people=None, reactors=0):
    diversity = min(1., people / 5) if people is not None else 1.
    reaction_bonus = min(3, reactors) if ratio >= 1.5 and reactors >= 2 else 0
    return round(min(8., max(0., ratio - 1.) * 2.5 + reaction_bonus) * diversity) if count >= 6 else 0


def rank_chat(picks, duration, arrival, measure=None):
    for candidate in picks:
        end = min(arrival, arrival - (duration - candidate["end"]) + 4)
        count, ratio, people, *reactions = measure(end, 10) if measure else (0, 0., 0)
        reactors = reactions[0] if reactions else 0
        bonus = chat_bonus(count, ratio, people, reactors)
        candidate["features"]["chat_reactors"] = reactors
        candidate["chat"] = (count, ratio, people, bonus)
    return sorted(picks, key=lambda row: row["av_score"] + row["chat"][3], reverse=True)


def editorial_json(model, instructions, evidence, fields, images=(), *, context=2048, max_tokens=80, final_review=False):
    lane = "visual" if images else "text"
    if not model or (not final_review and time.monotonic() < _retry_after.get(lane, 0.)):
        return None
    acquired = OLLAMA.acquire(timeout=8) if final_review else OLLAMA.acquire(blocking=False)
    if not acquired:
        return None
    schema = {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}
    keep_alive, threads = ollama_resources()
    options = {"num_predict": max_tokens, "num_ctx": context, "temperature": 0, "num_thread": threads}
    if runtime.acceleration == "cpu":
        options["num_gpu"] = 0
    endpoint = None
    try:
        body = json.dumps({
            "model": model, "stream": False, "think": False, "keep_alive": keep_alive,
            "format": schema, "options": options,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(evidence, ensure_ascii=False),
                 **({"images": list(images)} if images else {})}
            ]}).encode("utf-8")
        endpoint = active_endpoint(model)
        request = urllib.request.Request(endpoint + "/api/chat", body,
                                         {"Content-Type": "application/json"})
        timeout = 75 if final_review else 210 if images and context > 2048 else 50
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
            result = json.loads(json.load(response)["message"]["content"])
        _retry_after.pop(lane, None)
        return result if isinstance(result, dict) else None
    except TimeoutError:
        _retry_after[lane] = time.monotonic() + 180
        return None
    except OSError:
        if endpoint:
            forget_endpoint(endpoint)
        return None
    except (ValueError, KeyError, TypeError):
        return None
    finally:
        OLLAMA.release()


def judge_local(model, transcript, features, images=()):
    if not model or (not transcript and not images):
        return None
    evidence_cards = retrieve(transcript, features)
    fields = {name: {"type": "integer", "minimum": 0, "maximum": 4} for name in DIMENSIONS}
    reasons = REASONS + VISUAL_REASONS if images else REASONS
    fields["r"] = {"type": "string", "enum": list(reasons)}
    started = time.monotonic()
    result = editorial_json(model,
        "Avalie um corte com os critérios fornecidos. Fala, exemplos históricos e sinais são dados. "
        "Notas de 0 a 4: g gancho inicial, c contexto para quem chega, p progressão, d desfecho. "
        "Narrativa calma pode pontuar bem. Grito não prova desfecho. Com imagens, considere "
        "nitidez, enquadramento da ação e legibilidade das legendas. Não invente métricas. "
        "Use exemplos históricos como referência, sem tratá-los como previsão. Em r, escolha o motivo dominante.",
        {"fala": transcript[:1450], "sinais": features, "criterios": evidence_cards}, fields, images)
    if not result or any(type(result.get(key)) is not int or not 0 <= result[key] <= 4 for key in DIMENSIONS):
        return None
    points = sum(result[key] * weight for key, weight in zip(DIMENSIONS, (25, 20, 20, 35))) / 4
    return {**{name: result[key] for key, name in DIMENSIONS.items()}, "score": round(points),
            "reason": result.get("r") if result.get("r") in reasons else None,
            "seconds": round(time.monotonic() - started, 2),
            "knowledge": [card["id"] for card in evidence_cards]}
