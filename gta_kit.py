"""Local Modelar workflow for the user's GTA editing kit."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4
import wave
from zipfile import BadZipFile, ZipFile

from job_registry import ROOT, submit

KIT_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Codex Video/kits/gta6.json"
STARTER = ROOT / "biblioteca/kit-gta6-base.zip"
PREFIX = "Kit GTA 6 com Claude/"
GAMEPLAY = "assets/gameplay/gameplay-gta6.mp4"
FONTS = tuple(f"estilo/fontes/{name}.ttf" for name in ("ArchivoBlack-Regular", "Roboto", "Montserrat"))
SFX = ("assets/sfx/sons.json", *(f"assets/sfx/{name}.wav" for name in
       ("dinheiro", "glitch", "whoosh-cinematico", "riser", "pop", "clique", "relogio", "whoosh", "notificacao")))
MUSIC = tuple(f"assets/musicas/{name}.mp3" for name in
              ("musica-1-gta-trap", "musica-2-gta-trap-longa", "musica-3-game-streaming"))
DURATIONS = (20, 40, 60, 90)
FORMATS = ("Como fazer", "GTA 5 vs. GTA 6", "Lista de curiosidades", "Segredos", "Não faça isso",
           "Top 5", "Dinheiro", "O que acontece se…", "Easter eggs", "Realismo e detalhes")
QUESTIONS = ("Qual duração você prefere?", "Qual @ deve aparecer? Pode deixar em branco.",
             "Que formato e assunto você quer abordar?", "Que fatos observados ou fontes sustentam a ideia?",
             "Quer revisar um roteiro ou já tem as falas prontas?",
             "Qual gameplay e narração vamos usar?")
CATALOG = (
    (5, "rua caminhada cidade andando"), (27, "rua pedestres cidade movimento"),
    (75, "carro trânsito direção dirigindo"), (415, "celular telefone interface"),
    (525, "carro trânsito direção dirigindo"), (570, "carro estrada direção"),
    (641, "comida rua trailer"), (752, "ponte carro paisagem"),
    (798, "polícia viatura rua"), (925, "mapa menu interface"),
    (1080, "oficina carro garagem"), (1265, "pôr sol horizonte paisagem"),
)
TIMESTAMP = re.compile(r"^\[(\d{1,3}):(\d{2}(?:\.\d+)?)\]\s*")


def validate_archive(path, *, complete=True):
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ValueError("Escolha o ZIP original do Kit GTA 6.")
    with ZipFile(path) as archive:
        assets = (*FONTS, GAMEPLAY, *SFX, *MUSIC) if complete else FONTS
        for name in assets:
            limit = 550 * 1024**2 if name == GAMEPLAY else 12 * 1024**2
            entry = archive.getinfo(PREFIX + name)
            if entry.is_dir() or not 0 < entry.file_size <= limit or entry.flag_bits & 1:
                raise ValueError("O ZIP tem um recurso inválido ou protegido por senha.")
    return path


def registered_archive():
    try:
        path = Path(json.loads(KIT_STATE.read_text(encoding="utf-8"))["archive"])
        return validate_archive(path)
    except (BadZipFile, OSError, TypeError, ValueError, KeyError):
        pass
    try:
        return validate_archive(installed_archive(), complete=True)
    except (BadZipFile, OSError, ValueError, KeyError):
        pass
    try:
        return validate_archive(STARTER, complete=False)
    except (BadZipFile, OSError, ValueError, KeyError):
        return None


def installed_archive():
    return KIT_STATE.with_name("kit-gta6-completo.zip")


def register(path):
    try:
        archive = validate_archive(Path(path).resolve())
    except (BadZipFile, OSError, KeyError, ValueError) as error:
        raise ValueError("O ZIP precisa conter os arquivos do kit original.") from error
    KIT_STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = KIT_STATE.with_name(f".{uuid4().hex}.json")
    try:
        temp.write_text(json.dumps({"archive": str(archive)}, ensure_ascii=False), encoding="utf-8")
        temp.replace(KIT_STATE)
    finally:
        temp.unlink(missing_ok=True)
    return info()


def info():
    archive = registered_archive()
    return {"registered": bool(archive), "complete": bool(archive and archive != STARTER),
            "archive": archive.name if archive and archive != STARTER else "",
            "durations": DURATIONS, "formats": FORMATS, "questions": QUESTIONS}


def optional_effect(folder, name):
    """Stage a short sound from the registered kit, when it is available locally."""
    if name not in {"whoosh", "pop"}:
        raise ValueError("Efeito sonoro não reconhecido.")
    archive = registered_archive()
    if archive is None:
        return None
    try:
        with ZipFile(archive) as kit:
            source = kit.getinfo(PREFIX + f"assets/sfx/{name}.wav")
            if source.file_size > 2 * 1024**2:
                return None
            content = kit.read(source)
        if content[:4] != b"RIFF" or content[8:12] != b"WAVE":
            return None
        target = folder / f"kit-{name}.wav"
        target.write_bytes(content)
        return target
    except (BadZipFile, KeyError, OSError, RuntimeError):
        return None


def text_field(data, key, limit):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"Campo inválido ou longo demais: {key}.")
    return value.strip()


def brief(data):
    duration = data.get("duration")
    format_name = text_field(data, "format", 60)
    topic = text_field(data, "topic", 160)
    handle = text_field(data, "handle", 36)
    if duration not in DURATIONS or format_name not in FORMATS or not topic:
        raise ValueError("Escolha a duração, o formato e informe o assunto.")
    if handle and not re.fullmatch(r"@?[\w.-]{1,35}", handle):
        raise ValueError("Informe um @ com letras, números, pontos, hífens ou sublinhados.")
    return {"duration": duration, "format": format_name, "topic": topic, "handle": handle,
            "facts": text_field(data, "facts", 3000)}


def parse_scenes(script):
    scenes = []
    for line in script.splitlines():
        line = line.strip()
        if not line:
            continue
        match = TIMESTAMP.match(line)
        at = 60 * int(match[1]) + float(match[2]) if match else None
        spoken = line[match.end():].strip() if match else line
        if (match and float(match[2]) >= 60) or not re.search(r"\w", spoken) or len(spoken) > 170:
            raise ValueError("Cada cena precisa de uma fala curta e de um tempo válido, se informado.")
        scenes.append((spoken, at))
    if not 2 <= len(scenes) <= 40:
        raise ValueError("Informe entre 2 e 40 cenas, com uma fala por linha.")
    return scenes


def draft(data):
    from ai_setup import MODELS, installed_models
    from viral_rank import editorial_json

    setup = brief(data)
    if not setup["facts"]:
        raise ValueError("Adicione observações do gameplay ou fatos verificados para o roteiro.")
    models = installed_models() or set()
    model = next((name for name in MODELS if name in models), "")
    if not model:
        raise ValueError("Ative o Qwen no Ollama ou escreva as falas diretamente.")
    result = editorial_json(model, (
        "Você dirige um vídeo vertical em português do Brasil. Use apenas fatos e observações do briefing, "
        "não invente mecânicas, eventos ou dados. Abra com um gancho claro em uma frase curta, mantenha "
        "um assunto, avance a cada cena e revele o ponto prometido no final. Use cerca de 2 palavras por "
        "segundo e 1 fala curta por cena. Use *palavra* para destaque amarelo e **palavra** para rosa, "
        "com moderação. Retorne apenas falas, sem numeração, instruções de câmera ou marcações de tempo."
    ), setup, {"scenes": {"type": "array", "items": {"type": "string"}}}, context=3072, max_tokens=1000)
    lines = (result or {}).get("scenes")
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        raise ValueError("O Qwen não entregou um roteiro válido. Revise o briefing ou escreva as falas.")
    script = "\n".join(lines)
    parse_scenes(script)
    return {"script": script, "model": model}


def queue(data, output, origin):
    settings = brief(data)
    archive = registered_archive()
    if archive is None:
        raise ValueError("Importe o ZIP do Kit GTA 6 em Modelar.")
    complete = archive != STARTER
    script = text_field(data, "script", 6000)
    parse_scenes(script)
    if settings["format"] == "GTA 5 vs. GTA 6" and not data.get("gameplay"):
        raise ValueError("Selecione um gameplay próprio que já tenha as imagens comparadas.")
    if not complete and not data.get("gameplay"):
        raise ValueError("Escolha um gameplay próprio para usar o Kit GTA 6 incluído.")
    inputs = {}
    for field, extensions in (("gameplay", (".mp4", ".mkv", ".mov", ".webm")),
                              ("narration", (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"))):
        raw = text_field(data, field, 1000)
        if raw:
            path = Path(raw).resolve()
            if path.suffix.lower() not in extensions or not path.is_file():
                raise ValueError("Escolha um arquivo local válido de gameplay ou narração.")
            inputs[field] = str(path)
    row = submit({"sources": [str(archive), *inputs.values()], "output": str(output),
                  "gta_kit": {**settings, **inputs, "archive": str(archive), "script": script,
                              "complete": complete, "sound": complete and data.get("sound") is True,
                              "music": complete and data.get("music") is True}}, origin)
    return {"id": row["id"], "message": "Vídeo do Kit GTA 6 adicionado à fila."}


def run_process(args, stop, cwd, env=None):
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    with tempfile.TemporaryFile() as log:
        with subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=log, creationflags=flags) as child:
            while child.poll() is None:
                if stop.wait(0.3):
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
                    if child.poll() is None:
                        child.kill()
                    child.wait()
                    raise InterruptedError("Edição cancelada.")
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 5000))
            output = log.read().decode("utf-8", "replace").strip()
            if child.returncode:
                raise RuntimeError(output or f"Processo finalizado com código {child.returncode}.")
            return output


def local_voice(lines, folder, stop):
    voice_input = folder / "narração.json"
    voice_input.write_text(json.dumps([text.replace("*", "") for text, _ in lines], ensure_ascii=False), encoding="utf-8-sig")
    try:
        run_process(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                     str(ROOT / "scripts/gta_voice.ps1"), str(voice_input)], stop, folder)
    except (OSError, RuntimeError) as error:
        raise RuntimeError("Voz PT-BR do Windows indisponível. Selecione uma narração gravada.") from error
    destination = folder / "narracao.wav"
    timing = []
    cursor = 0.0
    with wave.open(str(destination), "wb") as target:
        for index in range(len(lines)):
            with wave.open(str(folder / f"voice-{index}.wav"), "rb") as source:
                if index == 0:
                    target.setparams(source.getparams())
                frames = source.readframes(source.getnframes())
                voice_end = cursor + source.getnframes() / source.getframerate()
                gap = 0.23 if index + 1 < len(lines) else 0.0
                padding = b"\0" * (int(source.getframerate() * gap) * source.getnchannels() * source.getsampwidth())
                target.writeframes(frames + padding)
                timing.append({"ini": cursor, "fim": voice_end + gap, "voz_ini": cursor, "voz_fim": voice_end})
                cursor = voice_end + gap
    return destination, timing


def stage_assets(archive, folder, names, stop, *, complete=True):
    with ZipFile(validate_archive(archive, complete=complete)) as source:
        required = sum(source.getinfo(PREFIX + name).file_size for name in names)
        if shutil.disk_usage(folder).free < required + 450 * 1024**2:
            raise ValueError("Libere espaço temporário para montar o vídeo do Kit GTA 6.")
        for name in names:
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(PREFIX + name) as incoming, target.open("wb") as out:
                for chunk in iter(lambda: incoming.read(1024**2), b""):
                    if stop.is_set():
                        raise InterruptedError("Edição cancelada.")
                    out.write(chunk)


def build_scenes(lines, data, has_own_gameplay, video_seconds, narration_seconds):
    used = set()
    scenes = []
    for index, (spoken, moment) in enumerate(lines):
        if moment is None:
            if has_own_gameplay:
                moment = index * min(4.0, video_seconds / len(lines))
            else:
                words = set(re.findall(r"\w+", spoken.lower()))
                pool = [(at, tags) for at, tags in CATALOG if at not in used and at < video_seconds - 3]
                if not pool:
                    used.clear()
                    pool = [(at, tags) for at, tags in CATALOG if at < video_seconds - 3]
                moment = max(pool, key=lambda item: len(words.intersection(item[1].split())), default=(0, ""))[0]
                used.add(moment)
        if moment >= video_seconds:
            raise ValueError("Um dos tempos marcados passa do fim do gameplay.")
        scene = {"fala": spoken, "inicio": min(moment, max(0, video_seconds - max(2, narration_seconds / len(lines)))),
                 "transicao": "punch" if index and index % 5 == 4 else "corte"}
        if index == 0:
            scene["efeitos"] = [{"tipo": "card", "titulo": data["topic"][:42], "em": 0.15, "dur": 1.55}]
        scenes.append(scene)
    return scenes


def render(request, event, register_session, stop):
    from engine import encoder, probe
    from runtime_profile import configure
    from workspace_data import register_exports

    configure("leve")
    data = request["gta_kit"]
    lines = parse_scenes(data["script"])
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=True)
    result = output / f"Kit GTA 6 - {uuid4().hex[:8]}" / "Clipes prontos"
    with tempfile.TemporaryDirectory(prefix=".gta-kit-", dir=output) as scratch:
        folder = Path(scratch)
        assets = [*FONTS]
        if not data.get("gameplay"):
            assets.append(GAMEPLAY)
        if data["sound"]:
            assets.extend(SFX)
        if data["music"]:
            assets.extend(MUSIC)
        event("Preparando os recursos locais do kit.")
        stage_assets(Path(data["archive"]), folder, assets, stop, complete=data.get("complete", True))
        gameplay = Path(data.get("gameplay") or folder / GAMEPLAY)
        video_seconds, _ = probe(gameplay, timeout=20)
        timing = None
        if data.get("narration"):
            voice = Path(data["narration"])
        else:
            event("Gerando narração com a voz local em português.")
            voice, timing = local_voice(lines, folder, stop)
        media = json.loads(run_process(["ffprobe", "-v", "error", "-select_streams", "a:0",
                                       "-show_entries", "format=duration:stream=codec_type", "-of", "json",
                                       str(voice)], stop, folder))
        if not media.get("streams"):
            raise ValueError("O arquivo de narração precisa ter áudio.")
        voice_seconds = float(media["format"]["duration"])
        if not 2 <= voice_seconds <= 120 or len(lines) * .45 > voice_seconds:
            raise ValueError("Use uma narração entre 2 e 120 segundos, com tempo para todas as falas.")
        if abs(voice_seconds - data["duration"]) > max(5, data["duration"] * .18):
            event(f"Narração de {voice_seconds:.0f}s para alvo de {data['duration']}s. A edição preserva a fala.")
        plan = {"audio": str(voice), "gameplay": str(gameplay), "arroba": data["handle"],
                "titulo": data["topic"], "cenas": build_scenes(lines, data, bool(data.get("gameplay")),
                                                             video_seconds, voice_seconds),
                "inscreva": False, "musica": "auto" if data["music"] else False,
                "efeitos_sonoros": data["sound"], "timing": timing}
        script = folder / "roteiro.json"
        script.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        ready = folder / "clip_01.mp4"
        command = [sys.executable, "-X", "utf8", str(ROOT / "vendor/gta_kit_renderer.py"),
                   str(script), "--saida", str(ready)]
        event("Editando cenas, legendas e efeitos em 9:16.")
        args = encoder(quality=21)
        env = {**os.environ, "CODEX_GTA_ASSETS": str(folder), "CODEX_GTA_ENCODER": json.dumps(args)}
        try:
            run_process(command, stop, folder, env)
        except RuntimeError:
            if not args[1].endswith(("_nvenc", "_amf", "_qsv")):
                raise
            event("Codificação por GPU indisponível. Tentando pelo processador.")
            env["CODEX_GTA_ENCODER"] = json.dumps(encoder(software_only=True, quality=21))
            run_process(command, stop, folder, env)
        duration, audio, size = probe(ready, timeout=20, include_size=True)
        if not audio or size != (1080, 1920) or abs(duration - voice_seconds) > 1:
            raise RuntimeError("O MP4 final não passou na verificação de áudio, duração e resolução.")
        inspection = run_process(["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostats", "-xerror",
                                  "-threads", "2", "-i", str(ready), "-an", "-filter_threads", "2", "-vf",
                                  "fps=4,scale=135:240,blackdetect=d=1:pic_th=0.90:pix_th=0.13", "-f", "null", "-"],
                                 stop, folder)
        if sum(float(value) for value in re.findall(r"black_duration:([\d.]+)", inspection)) > duration * .95:
            raise RuntimeError("O MP4 saiu quase todo escuro. Verifique o gameplay escolhido.")
        if stop.is_set():
            raise InterruptedError("Edição cancelada.")
        result.mkdir(parents=True)
        title = re.sub(r"[^\w -]", "", data["topic"]).strip()[:60].rstrip()
        final = result / f"clip_GTA 6 - {title or 'Vídeo'}.mp4"
        ready.replace(final)
        register_exports(output, [final])
        register_session(result.parent)
        event(f"MP4 pronto em Cortes gerados · {duration:.0f}s · 1080 × 1920.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("info", "import", "draft", "render"))
    parser.add_argument("file", nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "info":
            result = info()
        elif args.action == "import":
            result = register(args.file)
        else:
            from desktop_actions import output_dir

            data = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
            result = draft(data) if args.action == "draft" else queue(data, output_dir(), "Modelar / Kit GTA 6")
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
