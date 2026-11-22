"""Bounded timestamped transcription and editorial selection for recordings."""
import heapq
import json
import math

from viral_rank import candidates, judge_local
from replay_selection import detail
from vendor.openshorts.clip_selection import dedupe_overlapping


def select(source, folder, total, signals, options, model, stop, weights, log, viewer_clips=()):
    from engine import inspect, stamp, transcribe
    from workspace_data import topic

    output = folder / "transcricao.jsonl"
    readable = folder / "transcricao.txt"
    readable_scratch = readable.with_suffix(".txt.partial")
    scratch = output.with_suffix(".partial")
    line = []
    line_start = None
    best = []
    serial = 0
    audio_only = signals is None
    signals = signals or ()
    log("Transcrevendo gravação. Cada linha traz o tempo exato na fonte.")
    try:
        with (scratch.open("w", encoding="utf-8") as handle,
              readable_scratch.open("w", encoding="utf-8") as plain):
            def flush():
                if line:
                    plain.write(f"[{stamp(line_start)}] {' '.join(line)}\n")
                    line.clear()
            for start in range(0, int(total) + 1, 120):
                if stop():
                    raise InterruptedError("Transcrição cancelada.")
                end = min(start + 120., total)
                if end <= start:
                    break
                # Look back across block boundaries for selection without repeating captions.
                offset = max(0., start - min(60., options.duration))
                words = transcribe(source, offset, end, language=options.speech_language)
                for a, b, word in words:
                    if start <= (a + b) / 2 < end:
                        handle.write(json.dumps({"start": round(a, 3), "end": round(b, 3),
                                                 "time": stamp(a), "text": word}, ensure_ascii=False) + "\n")
                        if not line:
                            line_start = a
                        line.append(word)
                        if word.endswith((".", "?", "!")) or len(line) >= 16:
                            flush()
                if audio_only:
                    measured = inspect(source, end - offset, True, start=offset, video=False)
                    local = [(i * 2, 20 * math.log10(max(1., audio)), 0.)
                             for i, (audio, _, _) in enumerate(measured)]
                else:
                    local = [(at - offset, audio, motion) for at, audio, motion in signals if offset <= at < end]
                picks = candidates([(a-offset, b-offset, word) for a,b,word in words],
                                   local, end-offset, options.duration, start-offset)
                for moment in viewer_clips:
                    peak = moment["start"]
                    if start <= peak < end:
                        low = max(offset, peak - 4)
                        high = min(total, low + options.duration)
                        if high - low >= 8:
                            picks.append({"start": low - offset, "end": high - offset,
                                          "transcript": " ".join(word for a, b, word in words if low <= a < high),
                                          "features": {"motion": 0., "viewer_clips": 1,
                                                       "viewer_views": moment["views"]},
                                          "av_score": min(62, 46 + round(math.log2(1 + moment["views"])))})
                if audio_only:
                    for pick in picks:
                        pick["features"]["selection_source"] = "audio_transcript"
                for pick in sorted(picks, key=lambda row: row["av_score"], reverse=True)[:3]:
                    if not pick["transcript"] and pick["features"]["motion"] < 1.8 and not pick["features"].get("viewer_clips"):
                        continue
                    pick["start"] += offset
                    pick["end"] += offset
                    if model and pick["transcript"]:
                        pick["word_context"] = [w for w in words if pick["start"] - 4 <= w[0] < pick["end"] + 4][:150]
                    bias = weights.get(topic(pick["transcript"]), 0)
                    pick["av_score"] = max(0, min(100, pick["av_score"] + bias))
                    item = (pick["av_score"], serial, pick)
                    serial += 1
                    if len(best) < max(12, options.count * 4):
                        heapq.heappush(best, item)
                    else:
                        heapq.heappushpop(best, item)
                log(f"Transcrição · {stamp(end)} / {stamp(total)}")
            flush()
        scratch.replace(output)
        readable_scratch.replace(readable)
    finally:
        scratch.unlink(missing_ok=True)
        readable_scratch.unlink(missing_ok=True)
    shortlist = [dict(pick, predicted_score=pick["av_score"]) for _, _, pick in sorted(best, reverse=True)]
    distinct = sorted(dedupe_overlapping(shortlist), key=lambda row: row["av_score"], reverse=True)
    for pick in distinct[:min(4, options.count + 1)]:
        if stop():
            raise InterruptedError("Análise cancelada.")
        refined = detail(model, pick, options.duration, total)
        if refined:
            pick.update(refined)
            pick["transcript"] = " ".join(word for a, b, word in pick["word_context"]
                                         if a >= pick["start"] and b <= pick["end"])
        semantic = refined["semantic"] if refined else judge_local(model, pick["transcript"], pick["features"])
        if semantic:
            pick["semantic"] = semantic
            pick["av_score"] = round(.55 * pick["av_score"] + .45 * semantic["score"])
    for pick in distinct:
        pick.pop("word_context", None)
        pick["predicted_score"] = pick["av_score"]
    ranked = sorted(dedupe_overlapping(distinct), key=lambda row: row["av_score"], reverse=True)
    shortlist = ranked[:options.count]
    applied = sum("semantic" in pick for pick in distinct)
    log(f"Ollama · {applied} candidato(s) avaliados por gancho, contexto, progressão e desfecho."
        if applied else "Seleção de gravação concluída com sinais locais.")
    return [[(pick["start"], pick["end"])] for pick in shortlist], output, shortlist
