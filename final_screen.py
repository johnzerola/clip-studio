"""Evaluate rendered media before it enters the folder of publishable clips."""
import base64
import json
import os
import re
import subprocess
import statistics

from viral_rank import judge_local
from gemini_review import judge_gameplay, model_configured
from editorial_review import review
import runtime_profile as runtime


def edited_words(words, shots):
    """Move original word timestamps to the exported clip's timeline."""
    result = []
    cursor = 0.
    for start, end, _ in shots:
        for low, high, word in words:
            if start <= (low + high) / 2 < end:
                result.append((cursor + max(low, start) - start, cursor + min(high, end) - start, word))
        cursor += end - start
    return result


def evaluate(path, ff, run, expected, words, model, threshold, prior):
    from engine import SIGNAL_FILTER, inspect

    vision_model = str(prior.get("vision_model", ""))
    info = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))
    video = next((stream for stream in info["streams"] if stream["codec_type"] == "video"), {})
    duration = float(info["format"]["duration"])
    width, height = video.get("width", 0), video.get("height", 0)
    technical = width > 0 and height > 0 and width * 16 == height * 9 and abs(duration - expected) <= .15
    reason = "formato_ou_duracao"
    if technical:
        graph = ("[0:v:0]split[qc][sampling];"
                 "[qc]scale=180:320,blackdetect=d=1.2:pix_th=0.03:pic_th=0.99,freezedetect=n=-60dB:d=2.5[checked];"
                 f"[sampling]{SIGNAL_FILTER}[frames]")
        flags = [ff[0], "-hide_banner", "-nostdin", "-nostats", "-xerror",
                 "-threads", "2", "-i", str(path), "-filter_complex_threads", "2", "-filter_complex", graph,
                 "-map", "[checked]", "-map", "0:a?", "-f", "null", os.devnull,
                 "-map", "[frames]", "-t", str(duration), "-c:v", "rawvideo", "-threads", "1", "-f", "rawvideo", "pipe:1"]
        try:
            with runtime.media_slot():
                playback = subprocess.run(runtime.multimedia_args(flags), capture_output=True, timeout=180,
                                          **runtime.child_options())
            if playback.returncode:
                reason = "erro_de_decodificacao"
            elif b"black_start:" in playback.stderr:
                reason = "trecho_preto"
            elif b"freeze_start:" in playback.stderr:
                reason = "imagem_congelada"
            else:
                reason = ""
        except (OSError, subprocess.TimeoutExpired):
            reason = "erro_de_revisao_tecnica"
    if reason:
        return {"status": "rejected", "technical_ok": False, "threshold": threshold, "score": 0,
                "reason": reason, "recommendation": "weak"}

    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    transcript_source = "timeline"
    reuse = prior.get("reuse_transcript") and len(words) >= 6 and prior.get("correction") != "fala"
    if (model or vision_model) and has_audio and not reuse:
        from engine import speech_model_path, transcribe
        try:
            model_asr = "base" if prior.get("correction") == "fala" and speech_model_path("base", download=False) else None
            words = transcribe(path, 0, duration, model=model_asr, language=prior.get("speech_language", "auto"))
            transcript_source = "render"
        except (OSError, RuntimeError, subprocess.SubprocessError):
            pass
    transcript = " ".join(w for _, _, w in words)
    tokens = re.findall(r"\w+", transcript.casefold())
    pace = len(tokens) / duration
    speech_seconds = sum(max(0., min(1., end - start)) for start, end, _ in words)
    variety = len(set(tokens)) / max(1, len(tokens))
    observations = inspect(path, duration, has_audio, video_frames=playback.stdout)
    movements = [row[1] for row in observations]
    audio_peaks = [row[0] for row in observations]
    final_motion = max(movements, default=0)
    final_median = statistics.median(movements) if movements else 0
    if not prior.get("signals"):
        prior = {**prior, "raw_score": min(78, 18 + min(32, pace * 18) + min(28, final_motion * 7)),
                 "signals": {"motion": final_motion, "motion_median": final_median,
                             "reaction": max(audio_peaks, default=0) >= 2.5,
                             "opening": bool(re.search(r"[!?]", " ".join(w for _, _, w in words[:10])))}}
    signals = prior["signals"]
    motion = (float(signals.get("motion", 0)) + final_motion) / 2
    median_motion = (float(signals.get("motion_median", 0)) + final_median) / 2
    opening = float(signals.get("opening", False))
    preliminary = max(0., float(prior.get("raw_score", 0)) - float(prior.get("chat_bonus", 0)))
    narrative = 20 + min(24, pace * 13) + min(18, variety * 28) + 8 * opening
    sustained = sum(value >= 1.3 for value in movements) / max(1, len(movements))
    action = 16 + min(34, max(0, motion - .9) * 11) + min(22, preliminary * .32) + 12 * sustained
    features = {"phase": "edited", "duration": round(duration, 2), "word_count": len(tokens),
                "speech_seconds": round(speech_seconds, 1), "motion": round(motion, 2),
                "active_fraction": round(sustained, 2)}
    semantic = judge_local(model, transcript, features) if tokens and model != vision_model else None
    story_score = (.45 * narrative + .55 * semantic["score"] if semantic
                   else .62 * narrative + .38 * preliminary)
    # A short standalone line can score well, but it cannot carry a long quiet cut by itself.
    if speech_seconds < duration * .17:
        story_score -= min(18, max(0., duration - speech_seconds * 5) * .8)
    # Action has its own path when there's a sustained visual cue or an audible reaction.
    action_score = (.78 * action + .22 * preliminary
                    if motion >= 2.6 and (median_motion >= 1.12 or signals.get("reaction")) else 0.)
    best = "ação" if action_score > story_score else "narrativa"
    score = min(100, max(0, round(max(story_score, action_score))))
    local_score = score
    visual = None
    editorial = None
    gemini_gameplay = not tokens and model_configured()
    visual_provider = None
    if vision_model or gemini_gameplay:
        frames = []
        for at in (min(1.25, duration * .06), duration * .28, duration * .58, duration * .91):
            try:
                jpg = run([*ff, "-ss", str(at), "-threads", "1", "-i", str(path),
                           "-frames:v", "1", "-an", "-vf", "scale=288:512", "-c:v", "mjpeg",
                           "-threads", "1", "-f", "image2pipe", "pipe:1"], timeout=8)
                if jpg:
                    frames.append((round(at, 2), base64.b64encode(jpg).decode("ascii")))
            except (OSError, RuntimeError, subprocess.SubprocessError):
                continue
        if frames:
            editorial = review(vision_model, words, features, frames, threshold, retry=bool(prior.get("auto_finalize")),
                               stop=prior.get("stop"), log=prior.get("log"))
            if editorial:
                visual = editorial
                score = editorial["score"]
                visual_provider = "ollama_editorial"
            elif gemini_gameplay:
                visual = judge_gameplay([image for _, image in frames[:3]])
                if visual:
                    visual_provider = "gemini_visual"
                    score = round(.70 * score + .30 * visual["score"])
        if not visual and tokens and model and model == vision_model and not prior.get("auto_finalize"):
            semantic = judge_local(model, transcript, features)
            if semantic:
                score = round(.75 * score + .25 * semantic["score"])

    return {"status": "ready" if score >= threshold else "rejected", "technical_ok": True,
            "threshold": threshold, "score": score, "local_score": local_score, "narrative_rules": round(narrative),
            "action_rules": round(action), "review_path": best, "story_score": round(story_score),
            "action_score": round(action_score), "speech_seconds": round(speech_seconds, 2),
            "final_motion": round(final_motion, 3), "final_audio_peak_ratio": round(max(audio_peaks, default=0), 3),
            "model": model if semantic else None,
            "visual": visual, "vision_model": (visual.get("model") or vision_model) if visual else None,
            "editorial": editorial, "recommendation": editorial["recommendation"] if editorial else "pending",
            "review_engine": visual_provider or ("ollama_texto" if semantic else "regras_locais"),
            "transcript_source": transcript_source,
            "review_transcript": transcript[:1450],
            "semantic": semantic, "reason": "nota_suficiente" if score >= threshold else "abaixo_do_limiar"}
