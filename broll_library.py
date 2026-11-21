"""Catálogo local de imagens e vídeos para inserts editoriais."""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

STILLS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA = STILLS | {".gif", ".mp4", ".mov", ".webm"}
DIRECTOR_ROLES = {"broll", "gta", "meme", "meme-br", "background"}
DIRECTOR_RIGHTS = {"project-authored", "CC0", "CC-BY", "PDM", "authorized"}
REAL_SOURCES = {"camera", "photograph", "real-footage", "archival"}
GROUPS = {"GTA6": "GTA 6", "Memes": "Memes", "Gatinhos": "Gatinhos"}
CUES = {
    "gatinho ilustrado original": ("gato", "gatinho"),
    "gatinho acenando original": ("oi", "tchau", "até logo"),
    "cat glasses warning finger": ("cuidado", "atenção"),
    "cat green screen pointing": ("olha isso", "tá vendo"),
    "cat headphones energy drink": ("virou a noite", "energético"),
    "cat referee red card": ("cartão vermelho", "expulso"),
    "cat shushing closeup": ("silêncio", "fala baixo"),
    "cat surprised pointing yellow paw": ("que susto", "meu deus"),
    "cat thumbs up sparkles a": ("mandou bem", "boa demais"),
    "cat wallet empty paws": ("caro demais", "sem dinheiro"),
    "two cats green screen": ("dois gatos",),
    "emoji shrug thumbs up": ("sei lá",),
    "hamster pointing explosion pixel art": ("explosão", "explodiu"),
    "spider man looking at phone": ("celular",),
    "cat surprised detail": ("gato", "gatinho", "que susto"),
    "meme grupo do churrasco": ("churrasco",),
    "meme freela pix": ("pix", "freela"),
    "meme ajuste rapido": ("ajuste rápido",),
}


LABELS = {
    "cat surprised detail": "Gatinho surpreso (vídeo)",
    "cat glasses warning finger": "Gato dando um aviso",
    "cat green screen pointing": "Gato apontando",
    "cat headphones energy drink": "Gato de fone e energético",
    "cat referee red card": "Gato mostrando cartão vermelho",
    "cat shushing closeup": "Gato pedindo silêncio",
    "cat surprised pointing yellow paw": "Gato surpreso (imagem)",
    "cat thumbs up sparkles a": "Gato fazendo joinha",
    "cat wallet empty paws": "Gato com carteira vazia",
    "two cats green screen": "Dois gatos",
    "gatinho ilustrado original": "Gatinho ilustrado",
    "gatinho acenando original": "Gatinho acenando",
    "emoji shrug thumbs up": "Emoji dando de ombros",
    "hamster pointing explosion pixel art": "Hamster pixel art",
    "spider man looking at phone": "Homem-Aranha olhando o celular",
}


@dataclass(frozen=True)
class Asset:
    key: str
    path: Path
    group: str
    label: str
    cues: tuple[str, ...]
    role: str = ""
    digest: str = ""
    rights: str = ""
    license: str = ""
    attribution: str = ""

    def is_current(self):
        if not self.digest:
            return self.path.is_file()
        try:
            with self.path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest() == self.digest
        except OSError:
            return False

    def credit(self):
        return {"asset": self.key, "label": self.label, "role": self.role, "sha256": self.digest,
                "rights_status": self.rights, "license": self.license, "attribution": self.attribution}


def director_items(project, *, group="AI Video Director"):
    """Read approved files identified as real media in a project manifest."""
    root = Path(project).resolve(strict=True)
    manifest = root / "media-manifest.json"
    if not manifest.exists():
        return []
    if not manifest.resolve().is_relative_to(root) or manifest.stat().st_size > 8_000_000:
        raise ValueError("Manifesto de mídia do Director inválido.")
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schemaVersion") != 1 or not isinstance(data.get("assets"), list):
        raise ValueError("Formato de biblioteca do Director inválido.")
    items = []
    for item in data["assets"]:
        if not isinstance(item, dict):
            continue
        relative, digest = item.get("relativePath"), item.get("sha256")
        role, rights = item.get("role"), item.get("rightsStatus")
        if not (isinstance(relative, str) and isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest)
                and isinstance(role, str) and role in DIRECTOR_ROLES and isinstance(rights, str) and rights in DIRECTOR_RIGHTS):
            continue
        partial = Path(relative)
        if partial.anchor or ".." in partial.parts or partial.suffix.lower() not in MEDIA:
            continue
        path = (root / partial).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            continue
        original = item.get("originalName")
        label = Path(original).stem if isinstance(original, str) else re.sub(r"^[0-9a-f]{10}-", "", path.stem)
        cue = " ".join(re.sub(r"[_-]+", " ", label).casefold().split())
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        kind = item.get("sourceKind")
        if kind is not None and (not isinstance(kind, str) or kind not in REAL_SOURCES):
            continue
        if kind is None and not any(tag in REAL_SOURCES for tag in tags if isinstance(tag, str)):
            continue
        if any(tag.casefold() in {"ai-generated", "synthetic", "ia"} for tag in tags if isinstance(tag, str)):
            continue
        phrases = [tag.removeprefix("cue:").strip() for tag in tags if isinstance(tag, str)
                   and (tag.startswith("cue:") or " " in tag)]
        attribution = item.get("attribution") or item.get("author") or ""
        if rights == "CC-BY" and not attribution:
            continue
        source = item.get("sourceUrl") or item.get("source_url") or ""
        attribution = " · ".join(str(value) for value in (attribution, source) if value)
        items.append(Asset(partial.as_posix(), path, group, label,
                           tuple(dict.fromkeys((*CUES.get(cue, (cue,)), *phrases))), role, digest, rights,
                           str(item.get("license") or ""), attribution))
    return items


def library_items(folder, custom="", *, included=None):
    sources = [(key, label, folder / key, True) for key, label in GROUPS.items()] if folder is not None else []
    if included is not None:
        sources += [(f"incluida/{key}", label, included / key, True) for key, label in GROUPS.items()]
    if custom and Path(custom).is_dir():
        path = Path(custom).resolve()
        sources.append((str(path), "Minha pasta", path, False))
    assets = []
    for key, group, path, recursive in sources:
        files = path.rglob("*") if recursive else path.iterdir()
        for file in sorted(files):
            if file.suffix.lower() not in MEDIA or not file.is_file():
                continue
            name = re.sub(r"^[0-9a-f]{10}-", "", file.stem)
            title = re.sub(r"(_Video_Clip|-v\d+)$", "", name)
            label = re.sub(r"[_-]+", " ", title)
            cue = label.casefold()
            if key == "GTA6":
                cue = re.sub(r" \d+$", "", cue)
            label = LABELS.get(cue, label)
            if not recursive:
                cue = re.sub(r"^tela ", "", cue)
            if cue.startswith("trailer ") and key == "GTA6":
                cue = "trailer"
            aliases = CUES.get(cue, (cue,))
            if not recursive and (file.stem.casefold().startswith("tela-")):
                aliases += (file.stem[5:].casefold(),)
            elif not recursive:
                aliases += (file.stem.casefold(),)
            assets.append(Asset(f"{key}/{file.relative_to(path).as_posix()}", file.resolve(),
                                group, label, aliases))
    return sorted(assets, key=lambda asset: (asset.group, asset.label.casefold(), asset.key))


def configured_visuals(root, request):
    mode, background = request.get("visual_mode", "off"), request.get("visual_background", "original")
    if mode not in ("off", "local", "director") or background not in ("original", "cinema", "director", "file", "catalog"):
        raise ValueError("Escolha uma biblioteca e um fundo disponíveis.")
    custom = request.get("visual_folder") or ""
    if custom and mode != "off" and not Path(custom).is_dir():
        raise ValueError("A pasta de memes e B-roll não está disponível.")
    library = []
    backdrop = None
    bundled = []
    if mode != "off" or background == "catalog":
        from visual_catalog import catalog
        bundled = [asset for asset, enabled, _ in catalog(root) if enabled]
    if mode != "off":
        library.extend(asset for asset in bundled if asset.role != "background")
        library.extend(library_items(None, custom))
    if background == "catalog":
        backdrop = next((item for item in bundled if item.role == "background"), None)
        if not backdrop:
            raise ValueError("A foto de fundo do acervo está indisponível.")
    if background == "file":
        path = Path(request.get("visual_backdrop_path") or "").resolve()
        if path.suffix.lower() not in MEDIA or not path.is_file():
            raise ValueError("Escolha uma imagem ou um vídeo para o fundo.")
        backdrop = Asset(path.name, path, "Meu fundo", path.stem, (), "background")
    if "director" in (mode, background):
        project = request.get("director_project")
        if not project:
            raise ValueError("Escolha um projeto do AI Video Director para usar seus arquivos.")
        items = director_items(project)
        if mode == "director":
            library = [item for item in items if item.role != "background"] + library
        if background == "director":
            backdrop = next((item for item in items if item.role == "background"), None)
            if not backdrop:
                raise ValueError("O projeto do Director precisa de um fundo aprovado no manifesto.")
    return tuple(library), background, backdrop
