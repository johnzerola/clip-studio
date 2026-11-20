"""Comandos privados do aplicativo Windows. O navegador nunca escolhe um executável."""
import json
import os
import sys
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

from job_registry import ROOT, cancel, list_jobs, outputs, submit
from modelar_bridge import load_profile, make_request


def output_dir():
    try:
        prefs = json.loads((ROOT / "preferencias.local.json").read_text(encoding="utf-8-sig"))
        return str(Path(prefs.get("output_dir") or ROOT / "resultados").resolve())
    except (OSError, ValueError):
        return str(ROOT / "resultados")


def action(command, data):
    if command == "jobs":
        return [{"id": row["id"], "state": row["state"], "detail": row["detail"], "cancel": bool(row["cancel"])}
                for row in list_jobs(8)]
    if command == "cancel":
        cancel(data["id"])
        return {"message": "Pedido de cancelamento enviado."}
    if command == "open-live":
        from engine import live_source
        url, _ = live_source(data["url"].strip())
        os.startfile(url)
        return {"message": "Transmissão aberta no navegador."}
    if command == "open":
        clips = outputs(data["id"])["clips"]
        if not clips:
            raise ValueError("O trabalho ainda não tem clipe exportado.")
        os.startfile(clips[0])
        return {"message": "Vídeo aberto."}
    if command == "classic":
        import subprocess
        subprocess.Popen([sys.executable, str(ROOT / "painel.py")], cwd=ROOT)
        return {"message": "Controles avançados abertos."}
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if command == "update":
            from update_install import start_update, select_assets
            from update_check import check_for_update
            found = []
            worker = check_for_update(found.append)
            if worker:
                worker.join(15)
            if found:
                release = found[0]
                tag, _ = select_assets(release)
                if messagebox.askyesno("Atualização disponível", tag + "\n\n" + str(release.get("body") or "")[:900] + "\n\nInstalar agora?", parent=root):
                    start_update(ROOT, release)
                    return {"installing": True}
            return {}
        profile = None
        if command == "modelar":
            project = filedialog.askdirectory(parent=root, title="Projeto do AI Video Director")
            if not project:
                return {}
            preset = filedialog.askopenfilename(parent=root, initialdir=str(Path(project) / "analises/approved-techniques"),
                                               title="Técnica aprovada", filetypes=[("Perfil", "*.json")])
            if not preset:
                return {}
            profile = load_profile(project, preset)
        language = data.get("speech_language", "auto")
        if language not in ("auto", "pt", "en", "es"):
            raise ValueError("Idioma de fala inválido.")
        height = data.get("capture_height", 720)
        replay_height = data.get("replay_height", 1440)
        if command == "live":
            from engine import CAPTURE_HEIGHTS, live_source
            source, _ = live_source(data["url"].strip())
            if height not in CAPTURE_HEIGHTS:
                raise ValueError("Escolha 480p, 720p ou 1080p para capturar.")
            if replay_height not in (1080, 1440):
                raise ValueError("Escolha 1080p ou 1440p para os trechos do replay.")
        elif command in ("modelar", "render"):
            source = filedialog.askopenfilename(parent=root, title="Vídeo para montar em 9:16",
                                                filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.webm *.avi")])
            if not source:
                return {}
        else:
            raise ValueError("Ação desconhecida.")
        folder = filedialog.askdirectory(parent=root, initialdir=output_dir(), title="Salvar os cortes nesta pasta")
        if not folder:
            return {}
        request = {"sources": [source], "output": folder, "style": "dynamic", "seconds": 90,
                   "minutes": int(data.get("minutes", 5)), "smart_reframe": True, "performance": "leve"}
        if profile:
            request = make_request(profile, source, folder)
        if not 1 <= request.get("minutes", 5) <= 720:
            raise ValueError("Use de 1 a 720 minutos.")
        request["speech_language"] = language
        if command == "live":
            request.update(capture_height=height, review=True, model="qwen3.5:4b",
                           vision_model="qwen3.5:4b", replay_after_live=True, replay_height=replay_height, count=3)
        row = submit(request, "Hook Spark / " + command)
        result = {"message": "Trabalho adicionado à fila V9.", "id": row["id"]}
        if profile:
            result["profile"] = {key: profile[key] for key in ("preset_sha256", "source_hashes", "reference_shot_seconds")}
        return result
    finally:
        root.destroy()


if __name__ == "__main__":
    try:
        print(json.dumps(action(sys.argv[1], json.load(sys.stdin)), ensure_ascii=True))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

