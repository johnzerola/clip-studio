"""Private Hook Spark desktop actions backed by the shared Clip Studio V9 queue."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from hashlib import sha256

from job_registry import ROOT, ACTIVE, cancel, connect, get, job_activity, list_jobs, outputs, submit


def output_dir():
    try:
        prefs = json.loads((ROOT / "preferencias.local.json").read_text(encoding="utf-8-sig"))
        return Path(prefs.get("output_dir") or ROOT / "resultados").resolve()
    except (OSError, ValueError):
        return ROOT / "resultados"


def folders():
    return list(dict.fromkeys([output_dir(), *(Path(row["output"]) for row in list_jobs(100))]))


def pick(data):
    from tkinter import Tk, filedialog

    window = Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        if data.get("kind") == "folder":
            return {"path": filedialog.askdirectory(parent=window, initialdir=str(output_dir()), title="Salvar cortes em")}
        if data.get("kind") == "visual-library":
            return {"path": filedialog.askdirectory(parent=window, title="Pasta de memes e B-roll")}
        if data.get("kind") == "gta-kit":
            return {"path": filedialog.askopenfilename(parent=window, title="Importar Kit GTA 6", filetypes=[("Kit GTA 6", "*.zip")])}
        if data.get("kind") == "gta-narration":
            return {"path": filedialog.askopenfilename(parent=window, title="Escolher narração", filetypes=[("Áudio", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg")])}
        if data.get("kind") in ("visual-backdrop", "visual-asset"):
            return {"path": filedialog.askopenfilename(parent=window, title="Escolher mídia da biblioteca",
                                                       filetypes=[("Mídia", "*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mov *.webm")])}
        if data.get("kind") == "preset":
            project = filedialog.askdirectory(parent=window, title="Projeto do AI Video Director")
            if not project:
                return {}
            preset = filedialog.askopenfilename(parent=window, initialdir=str(Path(project) / "analises/approved-techniques"),
                                                title="Técnica aprovada", filetypes=[("Perfil", "*.json")])
            return {"project": project, "preset": preset} if preset else {}
        if data.get("kind") == "youtube":
            return {"path": filedialog.askopenfilename(parent=window, title="Aplicativo OAuth para computador", filetypes=[("JSON OAuth", "*.json")])}
        return {"paths": filedialog.askopenfilenames(parent=window, title="Escolher vídeos", filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.webm *.avi")])}
    finally:
        window.destroy()


def start_job(command, data):
    from ai_setup import installed_models, MODELS
    from jobs_cli import prepare

    request = {name: data[name] for name in ("sources", "output", "seconds", "count", "minutes", "threshold",
               "speech_language", "acceleration", "precompress", "capture_height", "replay_height",
               "live_poll_hours", "catchup", "replay_count", "replay_period", "replay_only", "replay_gib",
               "transcribe_recordings", "ranges", "style", "performance", "captions", "music", "mode", "review",
               "visual_mode", "visual_background", "visual_folder", "visual_backdrop_path")
               if name in data}
    request["output"] = request.get("output") or str(output_dir())
    request.update(smart_reframe=True, trim_inactive=True)
    profile = None
    if command == "modelar":
        from modelar_bridge import load_profile, make_request

        profile = load_profile(data["project"], data["preset"])
        tuned = make_request(profile, request["sources"][0], request["output"], request.get("ranges", ""))
        tuned.update(request)
        request = tuned
        request["director_project"] = str(Path(data["project"]).resolve())
    if command == "live":
        request.update(review=True, replay_after_live=bool(data.get("replay_after_live", True)))
        request["gta_kit_style"] = data.get("gta_kit_style") is True
    local_ai = request.get("review") and data.get("ollama_review", True) is True
    request["auto_finalize"] = bool(local_ai and command in ("render", "live") and not request.get("ranges"))
    model = ""
    if local_ai:
        models = installed_models() or set()
        model = next((item for item in MODELS if item in models), "")
        request.update(model=model, vision_model=model)
        if model and not request.get("effects_model"):
            request["effects_model"] = model
    sources, *_ = prepare(request)
    if command == "live":
        from engine import CAPTURE_RESERVE, capture_space

        destination = Path(request["output"]).resolve()
        volume = next(folder for folder in (destination, *destination.parents) if folder.is_dir())
        if not capture_space(volume):
            raise ValueError(f"Escolha uma unidade com pelo menos {CAPTURE_RESERVE // 1024**2} MiB livres para a captura.")
        if request.get("performance", "leve") == "leve" and not request.get("replay_only"):
            if sum(kind == "live" for _, kind, _ in sources) > 2:
                raise ValueError("No modo Leve, selecione até duas lives. Use Equilibrado se quiser capturar mais canais.")
    row = submit(request, "Hook Spark / " + command)
    result = {"message": "Trabalho adicionado à fila V9.", "id": row["id"]}
    if local_ai:
        result["message"] += (f" IA de montagem e revisão: {model}." if model else
                              " O motor vai verificar o Ollama antes de iniciar."
                              if request["auto_finalize"] and request.get("mode", "render") == "render" else
                              " Ollama sem modelo conectado. Usando montagem e revisão do V9.")
    if profile:
        result["profile"] = {key: profile[key] for key in ("preset_sha256", "source_hashes", "reference_shot_seconds")}
    return result


def edit_ranges(data):
    from tkinter import Tk
    from tkinter.simpledialog import askinteger
    from painel import parse_ranges, parse_time
    from trim_preview import open_trim, select_plan
    from jobs_cli import ensure_media_path

    ensure_media_path()
    marks = []
    root = Tk()
    root.withdraw()
    try:
        if data.get("from_plan") is True:
            selected = select_plan(root)
            if not selected:
                return {}
            source, cuts = selected
            index = 1 if len(cuts) == 1 else askinteger(
                "Escolher corte", "Qual corte do plano deseja abrir?", minvalue=1, maxvalue=len(cuts), parent=root)
            if index is None:
                return {}
            ranges = cuts[index - 1]
        else:
            source = Path(data["source"]).resolve(strict=True)
            ranges = parse_ranges(data.get("ranges") or "")
        if not source.is_file() or source.suffix.lower() not in {".mp4", ".mkv", ".mov", ".webm", ".avi"}:
            raise ValueError("Selecione um único vídeo local para marcar o trecho.")
        window = open_trim(root, source, ranges, marks.extend, parse_time)
        root.wait_window(window)
    finally:
        root.destroy()
    return {"ranges": ", ".join(f"{a:.3f}-{b:.3f}" for a, b in marks), "source": str(source.resolve())} if marks else {}


def session_details(key):
    result = outputs(key)
    with connect() as db:
        tail = [row[0] for row in db.execute(
            "SELECT line FROM events WHERE job=? ORDER BY seq DESC LIMIT 24", (key,))]
    plans = []
    for filename in result["plans"][:6]:
        path = Path(filename).resolve()
        try:
            if not path.is_relative_to(Path(result["session"])) or path.stat().st_size > 2_000_000:
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            clips = report.get("clips", [])
            technique = report.get("director_reference") or {}
            plans.append({"source": Path(report.get("original_source") or filename).name,
                          "cuts": len(clips), "rhythm": technique.get("reference_shot_seconds"),
                          "ranges": [[part["start"], part["end"]] for cut in clips[:1] for part in cut.get("parts", [])[:6]]})
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return {"events": list(reversed(tail)), "plans": plans}


def update_info(install=False):
    from update_check import VERSION, check_for_update
    from update_install import select_assets, start_update

    found = []
    check_for_update(found.append).join(12)
    if not found:
        return {"version": VERSION}
    release = found[0]
    tag, _ = select_assets(release)
    if install:
        if any(row["state"] in ACTIVE for row in list_jobs(1)):
            raise RuntimeError("Conclua ou cancele o trabalho ativo antes de atualizar.")
        start_update(ROOT, release)
        return {"message": "Instalando " + tag + "…"}
    return {"version": VERSION, "available": tag, "notes": str(release.get("body") or "")[:1500]}


def clip_record(key):
    from posting_queue import db_open
    from contextlib import closing

    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
        raise ValueError("Identificador de corte inválido.")
    for folder in folders():
        if not (folder / "postagens.sqlite3").is_file():
            continue
        with closing(db_open(folder)) as db:
            row = db.execute("SELECT * FROM clips WHERE id=? AND result='ready'", (key,)).fetchone()
            if row and row["path"]:
                path = Path(row["path"]).resolve()
                if path.is_relative_to(folder.resolve()) and path.is_file() and path.suffix.lower() == ".mp4":
                    return folder, path, row
    raise ValueError("Clipe exportado indisponível.")


def library(platform):
    from posting_queue import ranked

    rows = {}
    for folder in folders():
        if not (folder / "postagens.sqlite3").is_file():
            continue
        for item in ranked(folder, 30, platform=platform):
            if item["id"] in rows or item["result"] != "ready" or not item["path"]:
                continue
            path = Path(item["path"]).resolve()
            if path.is_relative_to(folder.resolve()) and path.is_file() and path.suffix.lower() == ".mp4":
                rows[item["id"]] = {key: item[key] for key in
                    ("id", "title", "description", "tags", "reason", "score", "weighted_score", "duplicate_of",
                     "vote", "feedback_points", "retention_points", "topic", "similar_title", "recommendation")}
    for key, path in exported_clips():
        title = path.stem[5:] if path.stem.startswith("clip_GTA 6 - ") else path.stem.replace("_", " ").replace("-", " ")
        rows[key] = {"id": key, "title": title.strip(),
                     "score": None, "weighted_score": None, "vote": "", "duplicate_of": None}
    return sorted(rows.values(), key=lambda row: (row.get("recommendation") != "recommended",
                         -(row["weighted_score"] if row["weighted_score"] is not None else -1)))[:60]


def exported_clips():
    from contextlib import closing
    from posting_queue import db_open

    for folder in folders():
        if not (folder / "postagens.sqlite3").is_file():
            continue
        with closing(db_open(folder)) as db:
            entries = db.execute("""SELECT e.path FROM clip_exports e WHERE NOT EXISTS
                                  (SELECT 1 FROM clips c WHERE c.path=e.path AND c.result='ready')
                                  ORDER BY rowid DESC LIMIT 60""").fetchall()
        for (value,) in entries:
            path = Path(value).resolve()
            if path.is_relative_to(folder.resolve()) and path.is_file() and path.suffix.lower() == ".mp4":
                yield "export-" + sha256(str(path).encode("utf-8")).hexdigest(), path


def desktop_job(row):
    result = outputs(row["id"], row=row)
    detail = row["detail"]
    if not detail and row["state"] == "completed" and not result["clips"]:
        detail = "Plano ou prévia pronta" if result["plans"] and not row["origin"].endswith(" / live") else "Nenhum clipe exportado"
    if row["origin"].endswith(" / live") and row["state"] in ("completed", "failed") and not result["clips"]:
        with connect() as db:
            messages = [item[0] for item in db.execute(
                "SELECT line FROM events WHERE job=? ORDER BY seq DESC LIMIT 32", (row["id"],))]
        if any("espaço insuficiente para captura" in line.casefold() or "Captura em pausa" in line for line in messages):
            detail = "Nenhum clipe · captura pausada por espaço em disco"
        elif any(line.startswith("Nenhum vídeo ao vivo") for line in messages):
            detail = "Nenhum clipe · o provedor não entregou vídeo ao vivo"
        elif any("descartado" in line.casefold() for line in messages):
            detail = "Nenhum clipe aprovado pela triagem"
    return {"id": row["id"], "state": row["state"], "detail": detail, "cancel": bool(row["cancel"]),
            "output": row["output"], "clip_count": len(result["clips"]), "has_session": bool(result["session"]),
            "activity": job_activity(row["id"]) if row["state"] == "running" else []}


def open_brave(url):
    relative = Path("BraveSoftware/Brave-Browser/Application/brave.exe")
    roots = (os.getenv(name) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"))
    browser = next((Path(root) / relative for root in roots if root and (Path(root) / relative).is_file()), None)
    browser = browser or shutil.which("brave.exe")
    if not browser:
        raise RuntimeError("Brave não encontrado. A captura local pode continuar normalmente.")
    subprocess.Popen([str(browser), url], stdin=subprocess.DEVNULL, close_fds=True)


def action(command, data):
    if command in ("render", "live", "modelar"):
        return start_job(command, data)
    if command.startswith("gta-kit-"):
        from gta_kit import draft, info, queue, register

        if command == "gta-kit-info":
            return info()
        if command == "gta-kit-import":
            return register(data["path"])
        if command == "gta-kit-draft":
            return draft(data)
        if command == "gta-kit-render":
            return queue(data, output_dir(), "Modelar / Kit GTA 6")
        if command == "gta-kit-status":
            row = get(data["id"])
            if row["origin"] != "Modelar / Kit GTA 6":
                raise ValueError("Trabalho do Kit GTA 6 não encontrado.")
            return {**desktop_job(row), "progress": session_details(data["id"])["events"][-1:]}
    if command == "pick":
        return pick(data)
    if command == "trim":
        return edit_ranges(data)
    if command == "job-details":
        return session_details(data["id"])
    if command in ("visual-library", "visual-media", "visual-import", "visual-enable"):
        from visual_catalog import activate, card, catalog, import_asset, item_for
        if command == "visual-library":
            return [card(*row) for row in catalog(ROOT)]
        if command == "visual-import":
            return {"id": import_asset(data)}
        if command == "visual-enable":
            activate(ROOT, data["id"], data["enabled"] is True)
            return {}
        asset, _, _ = item_for(ROOT, data["id"])
        if not asset.path.is_file():
            raise ValueError("Arquivo indisponível.")
        return {"file": str(asset.path)}
    if command in ("visual-reviews", "visual-review-media", "visual-review-queue"):
        from visual_review import get_review, previews, queue_review
        if command == "visual-reviews":
            return previews()
        if command == "visual-review-queue":
            return queue_review(data)
        _, path, record = get_review(data["job"], data["id"])
        preview = path.with_name(record["preview"]).resolve()
        if not preview.is_relative_to(path.parent.resolve()) or not preview.is_file():
            raise ValueError("Arquivo da prévia indisponível.")
        return {"file": str(preview)}
    if command == "storage":
        from storage_use import storage
        return storage(ROOT, folders())
    if command == "jobs":
        return {"jobs": [desktop_job(row) for row in list_jobs(8)], "output": str(output_dir())}
    if command == "cancel":
        cancel(data["id"])
        return {"message": "Pedido de cancelamento enviado."}
    if command == "open-live":
        from engine import live_source
        url, _ = live_source(data["url"].strip())
        open_brave(url)
        return {"message": "Link enviado ao Brave."}
    if command == "open":
        result = outputs(data["id"])
        target = result["session"] if data.get("folder") is True else next(
            (path for path in result["clips"] if Path(path).is_file()), None)
        if not target or not Path(target).exists():
            raise ValueError("O trabalho ainda não tem resultado disponível.")
        os.startfile(target)
        return {"message": "Resultado aberto."}
    if command in ("ai-status", "ai-start", "ai-install"):
        from ai_setup import MODELS, installed_models, install_model, official_executable, start_model_service
        if command == "ai-install":
            install_model(data["model"], lambda _: None)
        elif command == "ai-start":
            start_model_service()
        models = installed_models()
        return {"available": models is not None, "installed": bool(official_executable()),
                "models": [model for model in MODELS if model in (models or set())]}
    if command in ("update-status", "update-install"):
        return update_info(command == "update-install")
    if command in ("youtube-account", "youtube-connect"):
        from youtube_publish import account, connect
        if command == "youtube-connect":
            return {"channel": connect(data["client"])}
        return {"channel": (account() or {}).get("channel")}
    if command == "agenda":
        from agenda_panel import agenda_rows
        return list(dict.fromkeys(row for folder in folders() for row in agenda_rows(folder)))[:60]
    from posting_queue import STUDIOS
    platform = data.get("platform", "YouTube")
    if platform not in STUDIOS:
        raise ValueError("Selecione uma plataforma disponível.")
    if command == "clip-open-studio":
        os.startfile(STUDIOS[platform])
        return {"message": "Studio aberto no navegador."}
    if command == "library":
        return library(platform)
    if command == "clip-preview" and str(data.get("id", "")).startswith("export-"):
        for key, path in exported_clips():
            if key == data["id"]:
                return {"file": str(path)}
        raise ValueError("Clipe exportado indisponível.")
    if command in ("clip-preview", "schedule", "review", "reassess", "publish", "retention", "feedback", "thumbnail", "reframe-copy"):
        from publish_state import browser_draft, review_info
        folder, path, row = clip_record(data["id"])
        if command == "clip-preview":
            return {"file": str(path)}
        if command == "reassess":
            if any(job["state"] in ("queued", "running") for job in list_jobs(8)):
                raise ValueError("Revise a galeria com IA quando a sessão de captura e edição terminar.")
            from ai_setup import MODELS, installed_models
            from engine import FF, command as run, probe
            from final_screen import evaluate
            from posting_queue import save_editorial_review
            from viral_knowledge import load_history
            import runtime_profile

            models = installed_models() or set()
            model = next((name for name in MODELS if name in models), "")
            if not model:
                raise ValueError("Ative o Ollama e selecione um Qwen3.5 em Integrações.")
            runtime_profile.configure("leve", "auto")
            runtime_profile.lower_worker_priority()
            load_history(folder)
            previous = review_info(folder, row["id"])
            threshold = int(previous.get("threshold") or 60)
            verdict = evaluate(path, FF, run, probe(path)[0], [], model, threshold,
                               {"vision_model": model, "speech_language": "auto"})
            if verdict["recommendation"] == "pending":
                raise ValueError("A revisão multimodal ficou incompleta. A nota anterior foi preservada.")
            save_editorial_review(folder, row["id"], verdict)
            return {"score": verdict["score"], "recommendation": verdict["recommendation"],
                    "editorial": verdict.get("editorial")}
        if command == "thumbnail":
            from visual_clip_tools import suggest_thumbnail
            return suggest_thumbnail(path, str(data.get("title") or row["title"]), data.get("at"))
        if command == "reframe-copy":
            if any(job["state"] in ("queued", "running") for job in list_jobs(8)):
                raise ValueError("Salve o novo enquadramento assim que a sessão V9 terminar.")
            from visual_clip_tools import reframe_copy
            reframe_copy(folder, path, zoom=data["zoom"], x=data["x"], y=data["y"])
            return {"message": "Cópia com o novo enquadramento salva em Cortes gerados."}
        if command == "review":
            review = review_info(folder, row["id"])
            judgement = review.get("visual") or review.get("semantic") or {}
            return {"notes": review.get("reason", row["reason"]), "engine": review.get("review_engine"),
                    "source_size": review.get("source_size"), "output_size": review.get("output_size"),
                    "edit_model": review.get("edit_model"), "editorial_reason": judgement.get("reason"),
                    "knowledge": judgement.get("knowledge", []), "editorial": review.get("editorial"),
                    "attempts": review.get("attempts", []),
                    "transcript": str(review.get("studio_transcript") or "")[:12000],
                    "draft": browser_draft(folder, row["id"], platform)}
        if command == "retention":
            from posting_queue import retention
            retention(folder, row["id"], platform, float(data["value"]), int(data["views"]))
            return {"message": "Retenção registrada para calibrar a nota."}
        if command == "feedback":
            from posting_queue import feedback
            feedback(folder, row["id"], platform, data.get("vote", ""))
            return {"message": "Decisão registrada."}
        planned = datetime.fromisoformat(data["planned"])
        if planned <= datetime.now(tz=planned.tzinfo):
            raise ValueError("Escolha um horário no futuro.")
        title = str(data.get("title") or row["title"])[:95]
        caption = str(data.get("caption") or row["description"])[:2000]
        if command == "publish":
            when = planned.astimezone(timezone.utc).isoformat(timespec="seconds")
            if data.get("provider") == "upload-post":
                from studio_services import send_social
                message = send_social(folder, row["id"], platform, title, caption, when, data["profile"], data["key"])
                return {"message": message}
            if data.get("provider") != "youtube" or platform != "YouTube":
                raise ValueError("Escolha um serviço de envio compatível.")
            from publish_state import start_upload
            from youtube_publish import account, future_time
            saved = account()
            if not saved or saved["channel"]["id"] != data.get("channel"):
                raise ValueError("Conecte e confira a conta do YouTube antes de enviar.")
            when = future_time(planned.astimezone().strftime("%d/%m/%Y %H:%M"))
            result = start_upload(folder, row["id"], saved["channel"]["id"], when,
                                  {"title": title, "description": caption}, lambda _: None)
            return {"message": result["detail"] or result["state"], "failed": result["state"] in ("failed", "uncertain")}
        browser_draft(folder, row["id"], platform, {"title": title, "caption": caption,
                      "planned": planned.astimezone().isoformat(timespec="minutes")}, only_new=data.get("batch") is True)
        return {"message": "Rascunho salvo na agenda local."}
    raise ValueError("Ação desconhecida.")


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("Pedido inválido.")
        print(json.dumps(action(sys.argv[1], data), ensure_ascii=True))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
