"""Ponte local AI Video Director -> fila Clip Studio, sem motores residentes extras."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def load_profile(project, preset):
    root = Path(project).resolve(strict=True)
    path = Path(preset).resolve(strict=True)
    if not path.is_relative_to(root) or path.stat().st_size > 2_000_000:
        raise ValueError("O preset deve ficar no projeto e ter até 2 MB.")
    raw = path.read_bytes()
    record = json.loads(raw)
    if record.get("schema") != "approved-editing-technique-v1":
        raise ValueError("Selecione um preset aprovado em analises/approved-techniques.")
    profile = record.get("profile", {})
    if profile.get("schema") not in ("learned-editing-techniques-v2", "learned-editing-techniques-v3"):
        raise ValueError("Versão de perfil incompatível.")
    if profile.get("requiresHumanReview") is not True or profile.get("doesNotCopyShotSequence") is not True:
        raise ValueError("Falta a política de revisão e proveniência do perfil.")
    hashes = record.get("sourceHashes")
    if not isinstance(hashes, dict) or not 1 <= len(hashes) <= 100:
        raise ValueError("Preset sem fontes verificáveis.")
    for name, expected in hashes.items():
        source = (root / name).resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("Referência fora do projeto.")
        with source.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Referência modificada: {name}")
    profile_hashes = profile.get("sourceHashes")
    if not isinstance(profile_hashes, dict) or not profile_hashes or any(hashes.get(k) != v for k, v in profile_hashes.items()):
        raise ValueError("Proveniência do perfil diverge das fontes aprovadas.")
    target = profile.get("targetShotSeconds")
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or not 1.5 <= target <= 5.2:
        raise ValueError("Ritmo fora do intervalo suportado.")
    return {"schema": "clip-modelar-reference-v1", "preset_sha256": hashlib.sha256(raw).hexdigest(),
            "analysis_id": str(record.get("analysisId", "")), "source_hashes": hashes,
            "reference_shot_seconds": target, "notes": str(record.get("notes", ""))[:2000],
            "editing_engine": "clip-studio-v9", "rhythm_application": "review-only",
            "limitations": "Ritmo é referência para revisão. Cor, tipografia e movimentos inferidos não são aplicados automaticamente."}


def make_request(profile, source, output, ranges=""):
    media = Path(source).resolve(strict=True)
    if not media.is_file():
        raise ValueError("Escolha um vídeo local existente.")
    return {"sources": [str(media)], "output": str(Path(output).resolve()), "mode": "render",
            "performance": "leve", "style": "dynamic", "seconds": 90, "count": 1,
            "ranges": ranges, "captions": True, "music": True, "review": True,
            "modelar_reference": profile}


def show_dialog(parent, output):
    from tkinter import filedialog, messagebox
    project = filedialog.askdirectory(parent=parent, title="Projeto AI Video Director com referências aprovadas")
    if not project:
        return
    preset = filedialog.askopenfilename(parent=parent, title="Preset aprovado do AI Video Director",
        initialdir=str(Path(project) / "analises" / "approved-techniques"), filetypes=[("Preset JSON", "*.json")])
    if not preset:
        return
    def ready(profile):
        if not messagebox.askyesno("Modelar com Clip Studio V9",
            f"Referências verificadas. Ritmo observado: {profile['reference_shot_seconds']} s por plano.\n\n"
            "O ritmo fica como orientação de revisão. A edição usa o motor V9 com legendas, trilha e acabamento.\n\n"
            "Escolher um vídeo e iniciar um corte no modo Leve?", parent=parent):
            return
        source = filedialog.askopenfilename(parent=parent, title="Vídeo para editar com V9",
            filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.webm")])
        if not source:
            return
        from job_registry import submit
        job = submit(make_request(profile, source, output()), "Modelar / AI Video Director")
        messagebox.showinfo("Trabalho iniciado", "Acompanhe em Trabalhos CLI/MCP.\nID: " + job["id"], parent=parent)
    import queue
    import threading
    messages = queue.Queue()

    def verify():
        try:
            messages.put((load_profile(project, preset), None))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            messages.put((None, str(error)))

    def poll():
        try:
            profile, error = messages.get_nowait()
        except queue.Empty:
            parent.after(150, poll)
            return
        if error:
            messagebox.showerror("Modelar", error, parent=parent)
        else:
            try:
                ready(profile)
            except (OSError, ValueError, TypeError, AttributeError) as error:
                messagebox.showerror("Modelar", str(error), parent=parent)

    threading.Thread(target=verify, daemon=True, name="modelar-verify").start()
    parent.after(150, poll)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--preset", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ranges", default="")
    parser.add_argument("--submit", action="store_true", help="Iniciar render na fila comum ao painel/CLI/MCP")
    args = parser.parse_args()
    try:
        profile = load_profile(args.project, args.preset)
        if args.submit:
            if not args.source or not args.output:
                parser.error("Envio exige --source e --output.")
            from job_registry import submit
            profile = submit(make_request(profile, args.source, args.output, args.ranges), "Modelar / AI Video Director")
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
