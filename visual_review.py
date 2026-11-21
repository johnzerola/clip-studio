"""Save the reviewed cut, then re-render exactly that cut on approval."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
from uuid import uuid4

from broll_library import Asset


def asset_data(asset):
    return dict(asdict(asset), path=str(asset.path)) if asset else None


def asset_from(data):
    return Asset(**dict(data, path=Path(data["path"]))) if data else None


def save(path, record):
    pending = path.with_suffix(".partial")
    pending.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    pending.replace(path)


def assets_used(finishing, options):
    insert = finishing["visual_insert"]
    if not insert:
        return None
    asset = next((item for item in options.visual_library if str(item.path) == insert["path"]), None)
    return {**insert, "asset": asset_data(asset)} if asset else None


def snapshot(source):
    status = source.stat()
    return [status.st_size, status.st_mtime_ns]


def prepare_preview(source, folder, shots, words, options, hook, screening):
    from engine import render_clip
    import runtime_profile

    key = uuid4().hex
    path = folder / f"visual-review-{key}.json"
    preview = folder / f"preview-{key}.mp4"
    configuration = {key: value for key, value in asdict(options).items() if key not in
                     {"visual_library", "background_asset", "broll_assets", "visual_plan"}}
    before = snapshot(source)
    result = render_clip(source, preview, shots, words if options.captions else [],
                         replace(options, preview_resolution=True, compression="original"), hook, timing_words=words)
    insert = assets_used(result, options)
    record = {"id": key, "source": str(source), "snapshot": before, "preview": preview.name, "settings": configuration,
              "background": asset_data(options.background_asset), "shots": shots, "words": words, "hook": hook,
              "insertion": insert, "anchor": {key: insert[key] for key in ("shot", "offset", "at")} if insert else None,
              "screening": list(screening[:2]) if screening else ["", 60], "device": runtime_profile.acceleration,
              "revision": 1}
    save(path, record)


def records(job):
    if job["state"] != "completed" or not job["session"]:
        return
    batch, output = Path(job["session"]).resolve(), Path(job["output"]).resolve()
    if not batch.is_relative_to(output) or not batch.is_dir():
        return
    for path in (batch / "Clipes prontos").rglob("visual-review-*.json"):
        if not path.resolve().is_relative_to(batch) or path.stat().st_size > 2_000_000:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(record, dict) and re.fullmatch(r"[a-f0-9]{32}", str(record.get("id", ""))) and not record.get("exported"):
                yield path, record
        except (OSError, ValueError):
            continue


def get_review(job_id, review_id):
    from job_registry import get

    job = get(job_id)
    for path, record in records(job):
        if record["id"] == review_id and path.name == f"visual-review-{review_id}.json":
            return job, path, record
    raise ValueError("Prévia indisponível. Confira os trabalhos concluídos.")


def previews():
    from job_registry import list_jobs

    seen = {}
    for job in reversed(list_jobs(32)):
        for _, record in records(job):
            insert = record["insertion"]
            seen.setdefault(record["id"], {"id": record["id"], "job": job["id"], "revision": record["revision"],
                                           "label": record.get("hook") or Path(record["source"]).stem,
                                           "insertion": {"label": insert["label"], "at": insert["at"]} if insert else None})
    return list(reversed(seen.values()))[:24]


def queue_review(data):
    from job_registry import submit

    job, _, record = get_review(data["job"], data["id"])
    action = data.get("choice")
    if action not in ("replace", "remove", "export"):
        raise ValueError("Escolha manter, trocar ou remover a inserção.")
    row = submit({"sources": [record["source"]], "output": job["output"], "visual_review": record["id"],
                  "visual_job": job["id"], "visual_choice": action, "visual_asset": data.get("asset", "")},
                 "Revisão de inserções V9")
    return {"id": row["id"], "message": "Revisão adicionada à fila."}


def run_review(request, log, session, stop):
    from engine import Options, render_clip, probe, command, FF
    from editorial import Cleanup
    from job_registry import ROOT
    from posting_queue import enqueue
    from runtime_profile import configure
    from visual_catalog import item_for

    job, path, record = get_review(request["visual_job"], request["visual_review"])
    session(Path(job["session"]))
    source = Path(record["source"]).resolve(strict=True)
    if snapshot(source) != record["snapshot"]:
        raise ValueError("O vídeo original mudou. Gere a prévia novamente.")
    cfg = {**record["settings"], "review_visuals": False}
    cfg["cleanup"] = Cleanup(**cfg["cleanup"])
    options = Options(**cfg, background_asset=asset_from(record["background"]))
    shots, words, hook = record["shots"], record["words"], record["hook"]
    choice, chosen = request["visual_choice"], record["insertion"]
    if choice == "remove":
        chosen = None
    if choice == "replace":
        asset, _, _ = item_for(ROOT, request["visual_asset"])
        if asset.role == "background":
            raise ValueError("Selecione um GIF, meme ou B-roll para trocar a inserção.")
        anchor = record["anchor"]
        if not anchor:
            index = next((i for i, (a, b, _) in enumerate(shots) if b-a >= 2), None)
            if index is None:
                raise ValueError("O trecho é curto demais para uma inserção.")
            anchor = {"shot": index, "offset": .6, "at": sum(b-a for a, b, _ in shots[:index]) + .6}
        chosen = {**anchor, "id": asset.digest, "label": asset.label, "asset": asset_data(asset)}
        record["anchor"] = anchor
    exporting = choice == "export"
    visual_plan = (chosen["shot"], chosen["offset"], asset_from(chosen["asset"])) if chosen else None
    options = replace(options, preview_resolution=not exporting, visual_disabled=not chosen, visual_plan=visual_plan,
                      contextual_broll=False, compression=options.compression if exporting else "original")
    configure("leve", record.get("device", "auto"))
    dest = path.with_name(f"clip_review_{record['id'][:12]}.mp4") if exporting else path.with_name(record["preview"])
    pending = dest.with_name(f".pending-{record['id']}.mp4")
    try:
        log("Exportando o corte revisado." if exporting else "Atualizando a prévia.")
        result = render_clip(source, pending, shots, words if options.captions else [], options, hook, timing_words=words)
        if stop.is_set():
            return 0
        if exporting:
            from final_screen import evaluate

            model, minimum = record["screening"]
            duration, _ = probe(pending)
            verdict = evaluate(pending, FF, command, duration, words, model, minimum, {"speech_language": options.speech_language})
            if stop.is_set():
                return 0
            verdict.update(duration=duration, source=str(source), status="ready", visual_credits=result["visual_credits"],
                           studio_transcript=" ".join(word for _, _, word in words)[:1450])
            pending.replace(dest)
            enqueue(Path(job["output"]), dest, dest, verdict, verdict["studio_transcript"], hook, model)
            record["exported"] = dest.name
            save(path, record)
            path.with_name(record["preview"]).unlink(missing_ok=True)
        else:
            pending.replace(dest)
            record["insertion"] = chosen
            record["revision"] += 1
            save(path, record)
    finally:
        pending.unlink(missing_ok=True)
    return 0
