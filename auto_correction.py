"""Translate one editorial suggestion into a bounded V9 edit."""
from dataclasses import replace

from editorial import clean_ranges, quiet_live_edits


FALLBACK = {
    "sem_contexto": "contexto", "sem_desfecho": "desfecho", "video_confuso": "enquadramento",
    "fala_confusa": "fala",
}


def approved(verdict):
    return (verdict.get("technical_ok") and verdict.get("review_engine") == "ollama_editorial"
            and verdict.get("recommendation") == "recommended")


def manual_review_score(verdict):
    if not verdict.get("technical_ok") or approved(verdict):
        return None
    score = max(verdict["score"], verdict.get("local_score", 0))
    return score if score >= 65 else None


def attempt_data(verdict):
    editorial = verdict.get("editorial") or {}
    return {"score": verdict["score"], "recommendation": verdict.get("recommendation", "pending"),
            "reason": editorial.get("summary") or verdict["reason"]}


def correction(source, total, audio, shots, words, options, verdict, *, protect_edges=False):
    from engine import inspect, speech_model_path, transcribe

    review = verdict.get("editorial") or {}
    if not verdict.get("technical_ok") or not review:
        return None
    action = review.get("adjustment")
    blocker = review.get("blocker")
    if action in (None, "nenhum"):
        action = FALLBACK.get(blocker)
        if action not in ("contexto", "desfecho"):
            return None
    if blocker in FALLBACK and FALLBACK[blocker] != action:
        return None
    if action in ("contexto", "desfecho") and not protect_edges:
        start, end = shots[0][0], shots[-1][1]
        low, high = (max(0., start - 8.), start) if action == "contexto" else (end, min(total, end + 5.))
        if high - low >= 1.2:
            added = transcribe(source, low, high, language=options.speech_language) if audio else []
            # Prefer a phrase edge before/after the original edit. Keep the original action intact.
            if added and action == "contexto":
                low = max(low, added[0][0] - .15)
            elif added:
                high = min(high, added[-1][1] + .25)
            if high - low < .8:
                return None
            inset = "gamecam" if options.face else "game"
            new = [(low, high, inset), *shots] if action == "contexto" else [*shots, (low, high, inset)]
            return action, new, sorted([*words, *added]), options
    if action == "enquadramento":
        inset = "gamecam" if options.face else "game"
        new = [(a, b, inset) for a, b, _ in shots]
        settings = replace(options, smart_reframe=False, polish=False, visual_disabled=True, visual_plan=None,
                           contextual_broll=False, visual_background="original")
        if new != shots or settings != options:
            return action, new, words, settings
    if action == "fala" and audio:
        settings = replace(options, music="", auto_music=False, voice_polish=True, sfx="nenhum", look="classic")
        corrected = words
        if speech_model_path("base", download=False):
            corrected = [word for a, b, _ in shots for word in
                         transcribe(source, a, b, model="base", language=options.speech_language)] or words
        if settings != options or corrected != words:
            return action, shots, corrected, settings
    if action == "ritmo":
        edited = []
        for start, end, style in shots:
            bins = inspect(source, end - start, audio, options.face, start=start, normalized=False)
            edits = quiet_live_edits(start, end, bins, words, options.cleanup.noise, minimum=2.5)
            kept, _ = clean_ranges(start, end, edits, words)
            edited.extend((a, b, style) for a, b in kept)
        length = sum(b - a for a, b, _ in edited)
        if length >= 8 and sum(b - a for a, b, _ in shots) - length >= .8:
            return action, edited, words, options
    return None
