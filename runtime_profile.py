"""Resource profiles for one local Clip Studio process."""
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
from functools import lru_cache
import shutil


@dataclass(frozen=True)
class Profile:
    label: str
    whisper_threads: int
    max_renders: int
    quality: str
    dvr_threads: int
    quiet_pass: bool = False
    low_priority: bool = False


PROFILES = {
    "leve": Profile("Leve · uso diário", 1, 1, "480p,360p,best", 2, True, True),
    "equilibrado": Profile("Equilibrado · mais detalhe", 2, 4, "720p,480p,360p,best", 4),
}
active = PROFILES["equilibrado"]
acceleration = "auto"
cuda_transcription = True

GPU_ENCODERS = {
    "nvenc": ["-preset", "p4", "-rc", "vbr", "-cq", "{quality}", "-b:v", "0"],
    "qsv": ["-preset", "medium", "-global_quality", "{quality}"],
    "amf": ["-rc", "cqp", "-qp_i", "{quality}", "-qp_p", "{quality}", "-quality", "balanced"],
}


def configure(name, device="auto"):
    global active, acceleration
    if device not in ("auto", "cpu"):
        raise ValueError("Aceleração deve ser automática ou CPU.")
    active = PROFILES[name]
    acceleration = device
    return active


@lru_cache(maxsize=8)
def tested_encoder(ffmpeg, codec):
    for family, settings in GPU_ENCODERS.items():
        name = f"{codec}_{family}"
        args = ["-c:v", name, *(part.format(quality=22) for part in settings)]
        try:
            test = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-f", "lavfi",
                                   "-i", "color=black:s=320x180:r=24:d=0.2", "-vf", "format=nv12",
                                   *args, "-f", "null", "-"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=8, **child_options(hide=True))
            if test.returncode == 0:
                return family
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def hardware_encoder(codec, quality):
    ffmpeg = shutil.which("ffmpeg")
    if acceleration == "cpu" or not ffmpeg:
        return None
    family = tested_encoder(ffmpeg, codec)
    if family:
        return ["-c:v", f"{codec}_{family}", *(part.format(quality=quality) for part in GPU_ENCODERS[family])]


def child_options(*, force_low=False, hide=False):
    if os.name != "nt":
        return {}
    flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if active.low_priority or force_low else 0
    if hide:
        flags |= subprocess.CREATE_NO_WINDOW
    return {"creationflags": flags} if flags else {}


def multimedia_args(args):
    if not active.low_priority or not args or not Path(str(args[0])).stem.casefold() == "ffmpeg":
        return args
    adjusted = list(args)
    for index, arg in enumerate(adjusted[:-1]):
        if arg in ("-threads", "-threads:v", "-filter_threads", "-filter_complex_threads"):
            adjusted[index + 1] = "1"
    return adjusted


def ollama_resources():
    """Expire the local LLM shortly after a light-profile burst."""
    return ("30s", 1) if active.low_priority else ("5m", 2)


def lower_worker_priority():
    """Give the UI and foreground apps precedence over background inference."""
    if active.low_priority and os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentThread.restype = ctypes.c_void_p
        kernel.SetThreadPriority.argtypes = (ctypes.c_void_p, ctypes.c_int)
        kernel.SetThreadPriority(kernel.GetCurrentThread(), -1)
