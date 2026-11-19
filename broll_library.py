"""Catálogo local de imagens e vídeos para inserts editoriais."""
import re
from dataclasses import dataclass
from pathlib import Path

STILLS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA = STILLS | {".mp4", ".mov", ".webm"}
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


def library_items(folder, custom="", *, included=None):
    sources = [(key, label, folder / key, True) for key, label in GROUPS.items()]
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
