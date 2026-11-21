"""Private Hook Spark desktop actions backed by the shared Clip Studio V9 queue."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

from job_registry import ROOT, ACTIVE, active_sources, cancel, list_jobs, outputs, submit


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
        if data.get("kind") == "visual-backdrop":
            return {"path": filedialog.askopenfilename(parent=window, title="Imagem ou vídeo de fundo",
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
    if request.get("review"):
        models = installed_models() or set()
        model = next((item for item in MODELS if item in models), "")
        request.update(model=model, vision_model=model)
    prepare(request)
    row = submit(request, "Hook Spark / " + command)
    result = {"message": "Trabalho adicionado à fila V9.", "id": row["id"]}
    if profile:
        result["profile"] = {key: profile[key] for key in ("preset_sha256", "source_hashes", "reference_shot_seconds")}
    return result


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
                    ("id", "title", "description", "tags", "reason", "score", "weighted_score", "duplicate_of")}
    return sorted(rows.values(), key=lambda row: -row["weighted_score"])[:30]


def action(command, data):
    if command in ("render", "live", "modelar"):
        return start_job(command, data)
    if command == "pick":
        return pick(data)
    if command == "jobs":
        rows = list_jobs(8)
        return {"jobs": [{"id": row["id"], "state": row["state"], "detail": row["detail"], "cancel": bool(row["cancel"]),
                          "output": row["output"], "activity": active_sources(row["output"]) if row["state"] == "running" else []}
                         for row in rows], "output": str(output_dir())}
    if command == "cancel":
        cancel(data["id"])
        return {"message": "Pedido de cancelamento enviado."}
    if command == "open-live":
        from engine import live_source
        url, _ = live_source(data["url"].strip())
        os.startfile(url)
        return {"message": "Transmissão aberta no navegador."}
    if command == "open":
        result = outputs(data["id"])
        target = next((path for path in result["clips"] if Path(path).is_file()), result["session"])
        if not target or not Path(target).exists():
            raise ValueError("O trabalho ainda não tem resultado disponível.")
        os.startfile(target)
        return {"message": "Resultado aberto."}
    if command in ("ai-status", "ai-install"):
        from ai_setup import MODELS, installed_models, install_model
        if command == "ai-install":
            install_model(data["model"], lambda _: None)
        models = installed_models()
        return {"available": models is not None, "models": [model for model in MODELS if model in (models or set())]}
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
    if command in ("clip-preview", "schedule", "review", "publish", "retention"):
        from publish_state import browser_draft, review_info
        folder, path, row = clip_record(data["id"])
        if command == "clip-preview":
            return {"file": str(path)}
        if command == "review":
            review = review_info(folder, row["id"])
            return {"notes": review.get("reason", row["reason"]), "engine": review.get("review_engine"),
                    "transcript": str(review.get("studio_transcript") or "")[:12000],
                    "draft": browser_draft(folder, row["id"], platform)}
        if command == "retention":
            from posting_queue import retention
            retention(folder, row["id"], platform, float(data["value"]), int(data["views"]))
            return {"message": "Retenção registrada para calibrar a nota."}
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
                      "planned": planned.astimezone().isoformat(timespec="minutes")})
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
