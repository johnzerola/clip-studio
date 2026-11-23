"""Assemble source audio and create a measured, optionally ducked master."""
import json
import math
import re
import subprocess
import wave

import numpy as np

from finishing import audio_runs

RATE = 48000
CHANNELS = 2
VOICE = ("highpass=f=80,afftdn=nr=5:nf=-48:tn=1,"
         "equalizer=f=2800:t=q:w=1.2:g=1.4,"
         "acompressor=threshold=0.10:ratio=2.6:attack=12:release=150:makeup=1.35")
TARGET = "loudnorm=I=-16:TP=-1.5:LRA=7"


def pcm(read, source, start, duration):
    raw = read(["-ss", str(start), "-i", str(source), "-t", str(duration),
                "-vn", "-map", "0:a:0", "-ac", "2", "-ar", str(RATE), "-f", "s16le", "pipe:1"])
    data = np.frombuffer(raw, dtype="<i2").reshape(-1, CHANNELS)
    length = round(duration * RATE)
    return np.pad(data[:length], ((0, max(0, length-len(data))), (0, 0))).astype(np.float32)


def speech_gain(data):
    block = round(.16*RATE)
    used = (len(data)//block)*block
    if not used:
        return 1.
    rms = np.sqrt(np.mean((data[:used].reshape(-1, block, CHANNELS)/32768)**2, axis=(1,2)))
    active = rms[rms >= max(.008, float(np.max(rms))*.12)]
    if not len(active):
        return 1.
    reference = float(np.percentile(active, 65))
    db = np.clip(-22 - 20*np.log10(reference), -8, 9)
    return float(10**(db/20))


def program(read, source, shots, frames, path, jcut_ms, level=False):
    runs = audio_runs(shots, frames)
    edits = []
    gains = []
    output_time = 0
    previous_overlap = False
    with wave.open(str(path), "wb") as output:
        output.setparams((CHANNELS, 2, RATE, 0, "NONE", "not compressed"))
        for i, (start, end, duration) in enumerate(runs):
            data = pcm(read, source, start, duration)
            gain = speech_gain(data) if level else 1.
            gains.append(round(20*math.log10(gain), 2))
            data *= gain
            tail = min(round(.012*RATE), len(data)//3)
            if tail:
                if not previous_overlap:
                    data[:tail] *= np.linspace(0, 1, tail)[:, None]
                data[-tail:] *= np.linspace(1, 0, tail)[:, None]
            previous_overlap = False
            if i+1 < len(runs):
                next_start = runs[i+1][0]
                lead = min(jcut_ms/1000, duration/3, max(0, next_start))
                if lead >= .035 and abs(next_start-end) >= .55:
                    incoming = pcm(read, source, next_start-lead, lead)
                    rms = float(np.sqrt(np.mean(incoming**2))) / 32768
                    if rms >= .007 and len(incoming) <= len(data):
                        if level:
                            incoming *= speech_gain(pcm(read, source, next_start,
                                                       min(1., runs[i+1][2])))
                        theta = np.linspace(0, math.pi/2, len(incoming))[:, None]
                        data[-len(incoming):] = data[-len(incoming):]*np.cos(theta) + incoming*np.sin(theta)
                        previous_overlap = True
                        edits.append({"before_video_at": round(output_time+duration, 4),
                                      "lead_ms": round(1000*len(incoming)/RATE),
                                      "pre_roll_source": round(next_start-lead, 4)})
            output.writeframesraw(np.clip(data, -32768, 32767).astype("<i2").tobytes())
            output_time += duration
    return edits, gains


def make_mix(ff, run, scratch, duration, voice, music, music_db, cues, *, kit_sounds=()):
    inputs = ["-i", "program.wav"]
    graph = [f"[0:a]{VOICE if voice else 'anull'}[voice]"]
    sources = ["[voice]"]
    index = 1
    if music:
        inputs += ["-stream_loop", "-1", "-i", music]
        graph.append("[voice]asplit=2[lead][key]")
        graph.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,"
                     f"volume={music_db}dB,afade=t=in:d=0.25,"
                     f"afade=t=out:st={max(0,duration-.32)}:d=0.32[bed]")
        graph.append("[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=240[duck]")
        sources = ["[lead]", "[duck]"]
        index += 1
    if cues:
        inputs += ["-i", "cues.wav"]
        graph.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo[sfx]")
        sources.append("[sfx]")
        index += 1
    for path, at, gain in kit_sounds:
        label = f"[kit{index}]"
        inputs += ["-i", str(path)]
        graph.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,"
                     f"volume={gain}dB,adelay={round(at * 1000)}:all=1{label}")
        sources.append(label)
        index += 1
    graph.append("".join(sources) +
                 f"amix=inputs={len(sources)}:duration=first:normalize=0,"
                 "alimiter=limit=0.93:level=false:latency=true[mix]")
    run(ff + ["-y", *inputs, "-filter_complex", ";".join(graph), "-map", "[mix]",
              "-t", str(duration), "-c:a", "pcm_s16le", "mix.wav"], cwd=scratch)


def loudness_filter(ff, scratch):
    import runtime_profile as runtime

    args = [ff[0], "-hide_banner", "-nostats", "-i", "mix.wav", "-af",
            TARGET + ":print_format=json", "-f", "null", "-"]
    with runtime.media_slot():
        probe = subprocess.run(runtime.multimedia_args(args), cwd=scratch, capture_output=True, text=True,
                               check=True, **runtime.child_options())
    block = re.search(r'\{\s*"input_i".*?\}', probe.stderr, re.S)
    if not block:
        return TARGET
    m = json.loads(block.group())
    keys = {"measured_I": "input_i", "measured_TP": "input_tp", "measured_LRA": "input_lra",
            "measured_thresh": "input_thresh", "offset": "target_offset"}
    if not all(math.isfinite(float(m[key])) for key in keys.values()):
        return "anull"
    return TARGET + ":linear=true" + "".join(f":{flag}={m[key]}" for flag,key in keys.items())
