"""Assets synthesized for the V9 editing profile, triggered by the spoken subject."""
import wave
from pathlib import Path

import cv2
import numpy as np

from editorial import normalized

TOPICS = {
    "radio": ("RÁDIO DO JOGO", {"radio", "musica", "musicas"}),
    "ligacao": ("LIGANDO...", {"ligar", "liguei", "ligando"}),
    "missao": ("MISSÃO", {"missao", "objetivo"}),
}
RATE = 48000


def background_graph(layer, width, height, media_index=None):
    inner_width, inner_height = round(width * .9 / 2) * 2, round(height * .9 / 2) * 2
    portrait = f"{layer}scale={inner_width}:{inner_height}:flags=lanczos,setsar=1"
    if media_index is None:
        return (f";{portrait},pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x111b2d,"
                f"drawbox=x=(iw-{inner_width})/2-2:y=(ih-{inner_height})/2-2:"
                f"w={inner_width + 4}:h={inner_height + 4}:c=0x637c9c@0.55:t=2[editorial_bg]")
    return (f";[{media_index}:v]fps=30,scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
            f"crop={width}:{height},setsar=1,drawbox=c=black@0.24:t=fill[art];"
            f"{portrait}[foreground];[art][foreground]overlay=(W-w)/2:(H-h)/2[editorial_bg]")


def contextual_card(folder, shots, words):
    for index, (start, end, style) in enumerate(shots):
        if style not in {"split", "gamecam", "game"}:
            continue
        for at, _, word in words:
            if not start + .15 <= at <= end - .90:
                continue
            token = normalized(word)
            for name, (label, triggers) in TOPICS.items():
                if token in triggers:
                    path = Path(folder) / f"{name}.png"
                    draw_card(path, label)
                    return {index: (path, max(.15, min(at - start, end - start - 1.17)))}
    return {}


def draw_card(path, label):
    # OpenCV's Hershey fonts cover ASCII.
    from unicodedata import normalize

    text = normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    graphic = np.full((328, 580, 3), (27, 21, 16), dtype=np.uint8)
    gold, white = (83, 215, 255), (244, 243, 239)
    cv2.rectangle(graphic, (4, 4), (575, 323), gold, 3, cv2.LINE_AA)
    cv2.rectangle(graphic, (34, 38), (42, 112), gold, -1)
    cv2.putText(graphic, text, (64, 93), cv2.FONT_HERSHEY_DUPLEX, 1.7, white, 2, cv2.LINE_AA)
    for i, height in enumerate((25, 62, 102, 67, 125, 91, 57, 104, 75, 36, 69, 24)):
        x = 43 + i * 43
        cv2.rectangle(graphic, (x, 206 - height // 2), (x + 23, 206 + height // 2), gold, -1)
    if not cv2.imwrite(str(path), graphic):
        raise RuntimeError("Não foi possível gravar o cartão do assunto.")


def music_bed(path):
    """Create a loop from original oscillator tones and a restrained pulse."""
    t = np.arange(8 * RATE, dtype=np.float64) / RATE
    pulse = np.mod(t, .5)
    hit = np.minimum(pulse / .012, 1) * np.exp(-8 * pulse)
    envelope = np.sin(np.pi * t / 8) ** .35
    bed = envelope * (.115 * np.sin(2 * np.pi * 55 * t) +
                      .06 * np.sin(2 * np.pi * 82.5 * t) +
                      .045 * np.sin(2 * np.pi * 110 * t) * (.55 + .45 * np.sin(np.pi * t)) +
                      .085 * hit * np.sin(2 * np.pi * (96 * pulse - 35 * pulse ** 2)))
    with wave.open(str(path), "wb") as file:
        file.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        file.writeframes((bed * 32767).astype("<i2").tobytes())
    return path


def camera_move(layer, target, frames, amount, anchor, *, size=(720, 1280)):
    """Ease into the emphasis and, when there is room, settle before the cut."""
    attack = "min(on/8,1)"
    release = f"min(max(({frames}-1-on)/10,0),1)" if frames >= 42 else "1"
    zoom = f"1+{amount}*(1-cos(PI*{attack}))/2*(1-cos(PI*{release}))/2"
    x, y = anchor
    return (f";{layer}fps=30,scale=1440:2560:flags=lanczos,"
            f"zoompan=z='{zoom}':x='(iw-iw/zoom)*{x}':y='(ih-ih/zoom)*{y}':"
            f"d=1:s={size[0]}x{size[1]}:fps=30{target}")
