"""Compress local MP4s with FFmpeg and only replace a verified, smaller result."""
import argparse
import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
import runtime_profile as runtime
from tempfile import TemporaryDirectory

PROFILES = ("original", "compacto", "hevc")
FLAGS = ["-hide_banner", "-loglevel", "error", "-nostdin"]


@lru_cache(maxsize=2)
def available_encoder(codec):
    paths = [shutil.which("ffmpeg")]
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        packages = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Packages"
        paths.extend(str(p) for p in sorted(packages.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"), reverse=True))
    for exe in dict.fromkeys(paths):
        if exe:
            encoders = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, check=False,
                                      text=True, encoding="utf-8", errors="replace", timeout=12)
            if re.search(rf"\b{codec}\b", encoders.stdout):
                return exe
    return None


def metadata(path):
    info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], timeout=30))
    video = next(s for s in info["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic"))
    audio = sum(s["codec_type"] == "audio" for s in info["streams"])
    return info, video, (video["width"], video["height"], audio), float(info["format"]["duration"])


def compress(path, profile):
    if profile not in PROFILES:
        raise ValueError("Perfil de compressão desconhecido.")
    path = Path(path).resolve(strict=True)
    size = path.stat().st_size
    result = {"profile": profile, "before_bytes": size, "after_bytes": size, "applied": False}
    if profile == "original":
        return result
    codec = "libx264" if profile == "compacto" else "libx265"
    exe = available_encoder(codec)
    if not exe:
        return {**result, "reason": f"encoder {codec} indisponível"}
    info, video, stream_shape, duration = metadata(path)
    if sum(s["codec_type"] == "video" for s in info["streams"]) != 1 or video.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
        return {**result, "reason": "fonte HDR ou com múltiplas faixas de vídeo"}
    extra = ["-x265-params", "pools=2:frame-threads=2", "-tag:v", "hvc1"] if profile == "hevc" else []
    with TemporaryDirectory(prefix=".compress-", dir=path.parent) as scratch:
        target = Path(scratch) / path.name
        subprocess.run(runtime.multimedia_args([exe, *FLAGS, "-threads", "2", "-i", str(path), "-map", "0", "-c", "copy",
                        "-c:v:0", codec, "-preset", "fast", "-crf", "27" if profile == "hevc" else "24",
                        "-threads:v", "2", *extra, "-movflags", "+faststart", str(target)]),
                       capture_output=True, check=True, timeout=7200, **runtime.child_options())
        smaller = target.stat().st_size
        if smaller >= size:
            return {**result, "reason": "a nova codificação não reduziu o tamanho"}
        new_info, new_vid, new_shape, new_duration = metadata(target)
        if (new_shape != stream_shape or len(new_info["streams"]) != len(info["streams"])
                or abs(new_duration - duration) > .1 or new_vid.get("nb_frames") != video.get("nb_frames")):
            return {**result, "reason": "verificação de duração, quadros ou faixas falhou"}
        subprocess.run(runtime.multimedia_args([exe, *FLAGS, "-xerror", "-threads", "2", "-i", str(target),
                        "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"]),
                       capture_output=True, check=True, timeout=7200, **runtime.child_options())
        target.replace(path)
    return {**result, "applied": True, "after_bytes": smaller, "codec": new_vid["codec_name"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--profile", choices=PROFILES[1:], default="compacto")
    parser.add_argument("--in-place", required=True, action="store_true", help="Troca o MP4 apenas se a verificação passar")
    args = parser.parse_args()
    if args.source.suffix.lower() != ".mp4" or not args.source.is_file():
        parser.error("Informe um MP4 local existente.")
    try:
        print(json.dumps(compress(args.source, args.profile), ensure_ascii=False))
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError) as error:
        parser.exit(1, f"Compressão falhou. Arquivo preservado. {error}\n")


if __name__ == "__main__":
    main()
