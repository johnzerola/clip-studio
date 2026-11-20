"""Explicit social uploads and the optional local OpenShorts UGC backend."""
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
from uuid import UUID, uuid4

from posting_queue import db_open
from vendor.openshorts.social_platforms import PLATFORMS, upload_fields

SOCIAL_URL = "https://api.upload-post.com/api/upload"


def social_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS studio_social (
        clip TEXT NOT NULL, platform TEXT NOT NULL, profile TEXT NOT NULL,
        state TEXT NOT NULL, reference TEXT NOT NULL, planned TEXT NOT NULL,
        external_id TEXT NOT NULL, PRIMARY KEY(clip,platform,profile))""")


def social_states(folder, platform):
    with closing(db_open(folder)) as db, db:
        social_table(db)
        result = {}
        for row in db.execute("SELECT clip,state FROM studio_social WHERE platform=?", (platform.lower(),)):
            result[row["clip"]] = row["state"]
        return result


def send_social(folder, clip, platform, title, caption, when, profile, key, *, one_per_slot=False):
    import httpx

    platform = platform.lower()
    profile, key = profile.strip(), key.strip()
    if platform not in PLATFORMS or not profile or not key or not title.strip():
        raise ValueError("Selecione um destino compatível e informe título, perfil e chave do Upload-Post.")
    if when and datetime.fromisoformat(when) <= datetime.now(timezone.utc):
        raise ValueError("O agendamento precisa estar no futuro.")
    with closing(db_open(folder)) as db:
        row = db.execute("SELECT path FROM clips WHERE id=? AND result='ready'", (clip,)).fetchone()
    if not row or not row["path"]:
        raise ValueError("Escolha um clipe aprovado na galeria.")
    source = Path(row["path"])
    if source.suffix.lower() != ".mp4":
        raise ValueError("A publicação exige um arquivo MP4.")
    external_id = "clip-studio-" + uuid4().hex
    with source.open("rb") as media:
        if hashlib.file_digest(media, "sha256").hexdigest() != clip:
            raise ValueError("O arquivo mudou. Inspecione o vídeo e aprove novamente.")
        media.seek(0)
        with closing(db_open(folder)) as db, db:
            social_table(db)
            db.execute("BEGIN IMMEDIATE")
            if one_per_slot and db.execute(
                    "SELECT 1 FROM studio_social WHERE platform=? AND profile=? AND planned=? AND state!='rejected'",
                    (platform, profile, when)).fetchone():
                raise ValueError("Horário do piloto automático já ocupado.")
            previous = db.execute("SELECT state FROM studio_social WHERE clip=? AND platform=? AND profile=?",
                                  (clip, platform, profile)).fetchone()
            if previous and previous[0] != "rejected":
                raise ValueError("Já existe um envio para esse perfil e destino. Confira no Upload-Post.")
            db.execute("INSERT OR REPLACE INTO studio_social VALUES (?,?,?,'sending','',?,?)",
                       (clip, platform, profile, when or "", external_id))

        state, reference = "uncertain", ""
        fields = {"user": profile, "title": title[:100], "description": caption[:4900],
                  "platform[]": platform, "async_upload": "true", "external_id": external_id}
        fields.update(upload_fields([platform], title=title, description=caption,
                                    tiktok_post_mode="DIRECT_POST"))
        if when:
            fields["scheduled_date"] = when
        try:
            with httpx.Client(timeout=httpx.Timeout(120, connect=8), follow_redirects=False) as client:
                response = client.post(SOCIAL_URL, headers={"Authorization": f"Apikey {key}"},
                                       data=fields, files={"video": (source.name, media, "video/mp4")})
            if response.status_code in (400, 401, 403, 404, 422, 429):
                state = "rejected"
            elif response.is_success:
                data = response.json()
                reference = str(data.get("job_id") or data.get("request_id") or "")
                if reference and data.get("success", True) is not False:
                    state = "provider_scheduled" if when and data.get("job_id") else "provider_pending"
        except (httpx.HTTPError, TypeError, ValueError, AttributeError):
            pass
        finally:
            with closing(db_open(folder)) as db, db:
                db.execute("UPDATE studio_social SET state=?,reference=? WHERE external_id=?",
                           (state, reference, external_id))
    return {
        "provider_scheduled": "Agendamento recebido pelo Upload-Post. Confira a fila do serviço.",
        "provider_pending": "Envio recebido. Acompanhe no Upload-Post até a rede confirmar.",
        "rejected": "O serviço recusou. Confira o perfil, a conta conectada e o horário.",
        "uncertain": "Envio sem confirmação. Confira o Upload-Post antes de repetir.",
    }[state]


@dataclass(frozen=True)
class Autopilot:
    platform: str
    hour: str
    minimum: int
    profile: str
    key: str = field(repr=False)


def auto_publish(folder, clip, config):
    from youtube_publish import future_time

    with closing(db_open(folder)) as db, db:
        social_table(db)
        approved = db.execute("""SELECT c.title,c.description,c.tags,c.score FROM clips c
            LEFT JOIN clip_signatures s ON s.clip=c.id
            WHERE c.id=? AND c.result='ready' AND s.duplicate_of IS NULL""", (clip,)).fetchone()
        if not approved or approved["score"] < config.minimum:
            return ""
        if db.execute("SELECT 1 FROM studio_social WHERE clip=? AND platform=? AND profile=?",
                      (clip, config.platform, config.profile)).fetchone():
            return ""
        occupied = {row[0] for row in db.execute("""SELECT planned FROM studio_social
                    WHERE platform=? AND profile=? AND state!='rejected'""",
                                                 (config.platform, config.profile))}
    for offset in range(14):
        day = datetime.now() + timedelta(days=offset)
        try:
            slot = future_time(day.strftime("%d/%m/%Y") + " " + config.hour)
        except ValueError:
            continue
        if slot not in occupied:
            caption = "\n\n".join(item for item in (approved["description"], approved["tags"]) if item)
            return send_social(folder, clip, config.platform, approved["title"], caption,
                               slot, config.profile, config.key, one_per_slot=True)
    return "Piloto automático: os horários dos próximos 14 dias já estão ocupados."


def ugc_base(port):
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("Informe a porta local do OpenShorts.")
    return f"http://127.0.0.1:{port}"


def ugc_request(port, route, *, body=None, headers=None):
    import httpx
    try:
        with httpx.Client(timeout=12, trust_env=False) as client:
            response = (client.post(ugc_base(port) + route, json=body, headers=headers)
                        if body is not None else client.get(ugc_base(port) + route, headers=headers))
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        raise RuntimeError("OpenShorts local indisponível. Inicie o backend da cópia no G:.") from None
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("O backend OpenShorts recusou ou interrompeu a operação. Confira o servidor local.") from None


def start_ugc(port, title, narration, actor, mode, fal_key, voice_key, voice_id=""):
    narration = narration.strip()
    if not (title.strip() and 8 <= len(narration) <= 1000 and actor.strip() and fal_key and voice_key):
        raise ValueError("Preencha título, roteiro de 8 a 1.000 caracteres, ator fictício e as duas chaves.")
    if mode not in ("lowcost", "premium"):
        raise ValueError("Modo UGC inválido.")
    script = {"title": title.strip()[:100], "language": "pt-BR", "full_narration": narration,
              "segments": [{"narration": narration, "visual_type": "talking_head"}]}
    payload = {"script": script, "actor_description": actor.strip(), "video_mode": mode,
               "share_to_gallery": False}
    if voice_id.strip():
        payload["voice_id"] = voice_id.strip()
    result = ugc_request(port, "/api/saasshorts/generate", body=payload,
                         headers={"X-Fal-Key": fal_key, "X-ElevenLabs-Key": voice_key})
    return str(UUID(result["job_id"]))


def ugc_status(port, job_id):
    job_id = str(UUID(job_id))
    result = ugc_request(port, f"/api/saasshorts/status/{job_id}")
    url = (result.get("result") or {}).get("video_url") or ""
    path = f"/videos/saas_{job_id}/"
    if url.startswith(path) and re.fullmatch(r"[\w.-]+\.mp4", url[len(path):]):
        result["preview"] = ugc_base(port) + url
    return result


def download_ugc(port, job_id, destination):
    import httpx
    from tempfile import TemporaryDirectory
    from engine import probe

    reply = ugc_status(port, job_id)
    if reply.get("status") != "completed" or not reply.get("preview"):
        raise ValueError("O servidor ainda não tem um MP4 concluído para este trabalho.")
    destination = Path(destination)
    with TemporaryDirectory(dir=destination.parent) as folder:
        pending = Path(folder) / "ugc.mp4"
        with httpx.stream("GET", reply["preview"], timeout=60, trust_env=False) as response:
            response.raise_for_status()
            with pending.open("wb") as handle:
                for data in response.iter_bytes():
                    handle.write(data)
                    if handle.tell() > 512 * 1024**2:
                        raise ValueError("O arquivo do ator ultrapassou 512 MiB.")
        if probe(pending)[0] <= 0:
            raise RuntimeError("O servidor não retornou um vídeo válido.")
        pending.replace(destination)
    return destination
