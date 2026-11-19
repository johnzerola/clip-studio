"""Offline synthesized sound effects and FFmpeg transitions."""
import argparse
import json
import math
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np

ROOT = Path(__file__).resolve().parent
PREVIEWS = ROOT / "work" / "effect-previews"
RATE = 48000
SOUNDS = {
    "whoosh": "Passagem curta para troca de cena",
    "radio": "Dois pulsos agudos para entrada de gráfico",
    "impacto": "Batida grave curta para um close de reação",
    "resolucao": "Sinal tonal curto para fechar uma ideia",
}
TRANSITIONS = {
    "corte": {"description": "Corte direto", "live": True, "xfade": None},
    "linha": {"description": "Faixa dourada passa pela entrada, sem sobrepor o áudio", "live": True, "xfade": None},
    "zoom": {"description": "Punch-in de 4% no início e 9% no close de destaque", "live": True, "xfade": None},
    "dissolve": {"description": "Dissolve entre dois planos", "live": False, "xfade": "fade"},
    "slide": {"description": "Deslize lateral entre dois planos", "live": False, "xfade": "slideleft"},
    "wipe": {"description": "Revelação lateral entre dois planos", "live": False, "xfade": "wipeleft"},
}


def catalog():
    return {"origin": "sons sintetizados localmente, sem samples externos",
            "sounds": SOUNDS, "transitions": TRANSITIONS}


def sound(name, peak_db=-8):
    if name not in SOUNDS or not -24 <= peak_db <= -3:
        raise ValueError("Escolha um som e pico de −24 a −3 dBFS.")
    duration = {"whoosh": .20, "radio": .22, "impacto": .25, "resolucao": .24}[name]
    t = np.arange(round(duration * RATE)) / RATE
    envelope = np.minimum(1, t/.009) * np.clip((duration-t)/.045, 0, 1)
    if name == "whoosh":
        noise = np.random.default_rng(211).normal(0, 1, len(t))
        noise = np.convolve(noise, np.ones(12)/12, mode="same")
        values = .63*noise + .3*np.sin(2*np.pi*(220*t+810*t*t))
        envelope *= np.sin(np.pi*np.clip(t/duration,0,1))**.7
    elif name == "radio":
        b = np.maximum(t-.073, 0)
        values = (np.sin(2*np.pi*850*t)*np.exp(-t*30)
                  + .83*np.sin(2*np.pi*1230*b)*np.exp(-b*31)*(t>=.073))
    elif name == "impacto":
        values = (np.sin(2*np.pi*(180*t-240*t*t)) + .28*np.sin(2*np.pi*570*t))*np.exp(-t*17)
    else:
        values = (.8*np.sin(2*np.pi*415*t)+.6*np.sin(2*np.pi*622*t))*np.exp(-t*17)
    wave_data=values*envelope
    return (wave_data * (10**(peak_db/20) / max(float(np.max(np.abs(wave_data))), 1e-6))).astype(np.float32)


def render_cues(path, duration, cues, peak_db=-8):
    if not 0 < duration <= 3600:
        raise ValueError("Duração fora do limite.")
    track = np.zeros(math.ceil(duration*RATE), dtype=np.float32)
    for timestamp, name, *gain in cues:
        data = sound(name, gain[0] if gain else peak_db)
        start = max(0, round(timestamp*RATE))
        size = max(0, min(len(data), len(track)-start))
        track[start:start+size] += data[:size]
    with wave.open(str(path),"wb") as file:
        file.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        file.writeframes(np.clip(track*32767,-32767,32767).astype("<i2").tobytes())
    return path


def edge_transition(layer, target, start=0., duration=.18, height=1280, tag="edge"):
    end = start+duration
    return (f";color=c=0xFFD166:s=12x{height}:r=30,format=rgba,colorchannelmixer=aa=0.68[{tag}];"
            f"{layer}[{tag}]overlay=x='(W+w)*(t-{start:.4f})/{duration:.4f}-w':y=0:"
            f"enable='between(t,{start:.4f},{end:.4f})'{target}")


def new_preview(suffix):
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    return PREVIEWS / (uuid4().hex[:12] + suffix)


def preview_transition(name):
    from engine import FF, command, encoder

    if name not in TRANSITIONS:
        raise ValueError("Transição desconhecida.")
    target = new_preview(".mp4")
    inputs = ["-f","lavfi","-i","testsrc2=s=360x640:r=30:d=1.5",
              "-f","lavfi","-i","smptebars=s=360x640:r=30:d=1.5"]
    effect = TRANSITIONS[name]["xfade"]
    if effect:
        graph = f"[0:v][1:v]xfade=transition={effect}:duration=0.30:offset=1.20[out]"
    else:
        graph = "[0:v][1:v]concat=n=2:v=1:a=0[cut]"
        if name == "linha":
            graph += edge_transition("[cut]", "[out]", start=1.43, height=640)
        elif name == "zoom":
            graph += (";[cut]zoompan=z='if(lt(on,45),1,1+0.09*(1-exp(-(on-45)/4)))':"
                      "x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=360x640:fps=30[out]")
        else:
            graph += ";[cut]null[out]"
    command(FF + ["-y", *inputs, "-filter_complex_threads","1","-filter_complex",graph,
                  "-map","[out]","-an","-pix_fmt","yuv420p", "-t","3"] + encoder() + [str(target)])
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    cmds=parser.add_subparsers(dest="action",required=True)
    cmds.add_parser("listar")
    s=cmds.add_parser("som");s.add_argument("name",choices=SOUNDS);s.add_argument("--pico",type=int,default=-8)
    v=cmds.add_parser("transicao");v.add_argument("name",choices=TRANSITIONS)
    args=parser.parse_args()
    if args.action=="listar":
        print(json.dumps(catalog(),ensure_ascii=False,indent=2))
    elif args.action=="som":
        print(render_cues(new_preview(".wav"), .3, [(0,args.name)], args.pico))
    else:
        print(preview_transition(args.name))


if __name__=="__main__":
    main()
