"""Compress local MP4s with FFmpeg and only replace a verified, smaller result."""
import argparse
import json
import os
import math
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


def reference_quality(original, candidate, duration):
    """Compare three short source-aligned excerpts while preserving the source dimensions."""
    enc = shutil.which("ffmpeg")
    filters = subprocess.check_output([enc, "-hide_banner", "-filters"], timeout=10).decode(errors="replace")
    metric, threshold = ("libvmaf", 94.0) if re.search(r"\blibvmaf\b", filters) else ("ssim", .985)
    pattern = r"VMAF score:\s*([\d.]+)" if metric == "libvmaf" else r"All:([\d.]+)"
    graph = ("[0:v]fps=15,scale=640:-2:flags=area,format=yuv420p,setpts=PTS-STARTPTS[test];"
             "[1:v]fps=15,scale=640:-2:flags=area,format=yuv420p,setpts=PTS-STARTPTS[ref];"
             f"[test][ref]{metric}")
    if metric == "libvmaf":
        graph += "=n_threads=1"
    scores = []
    for ratio in (.10, .50, .85):
        at = str(max(0., min(duration - 1.4, duration * ratio)))
        result = subprocess.run([enc, *FLAGS, "-loglevel", "info", "-threads", "1", "-ss", at, "-t", "1.4",
                                 "-i", str(candidate), "-threads", "1", "-ss", at, "-t", "1.4", "-i", str(original),
                                 "-an", "-filter_complex_threads", "1", "-filter_complex", graph, "-f", "null", "-"],
                                capture_output=True, check=True, timeout=35, **runtime.child_options(hide=True))
        matches = re.findall(pattern, result.stderr.decode(errors="replace"))
        if not matches:
            return {"metric": metric, "accepted": False}
        score = float(matches[-1])
        if not math.isfinite(score):
            return {"metric": metric, "accepted": False}
        scores.append(score)
    return {"metric": metric, "minimum": round(min(scores), 4), "accepted": min(scores) >= threshold}


PRECOMPRESSION_BYTES = 100_000_000


def prepare_source(source, scratch, log):
    """Return a verified, smaller editing copy for a large source when the quality permits it."""
    size = source.stat().st_size
    if size < PRECOMPRESSION_BYTES:
        return source
    if shutil.disk_usage(scratch).free < size + 512 * 1024**2:
        log("Pré-compressão dispensada por espaço insuficiente para a cópia de edição.")
        return source
    info, video, shape, duration = metadata(source)
    if (sum(s["codec_type"] == "video" for s in info["streams"]) != 1
            or video.get("color_transfer") in {"smpte2084", "arib-std-b67"}
            or video.get("pix_fmt") != "yuv420p"
            or video.get("side_data_list")):
        return source
    choices = []
    for codec, q in (("hevc", 19), ("h264", 18)):
        args = runtime.hardware_encoder(codec, q)
        if args:
            choices.append((shutil.which("ffmpeg"), args))
            break
    if exe := available_encoder("libx264"):
        choices.append((exe, ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]))
    if not choices:
        log("Pré-compressão indisponível neste FFmpeg. Editando a fonte original.")
        return source
    target = scratch / "edicao.mp4"
    for exe, args in choices:
        try:
            subprocess.run(runtime.multimedia_args([exe, *FLAGS, "-y", "-threads", "2", "-i", str(source),
                           "-map", "0:v:0", "-map", "0:a?", *args, "-c:a", "copy",
                           "-threads:v", "2", "-movflags", "+faststart", str(target)]),
                           capture_output=True, check=True, timeout=7200,
                           **runtime.child_options(force_low=True, hide=True))
            if target.stat().st_size >= size * .80:
                break
            post, stream, output_shape, output_duration = metadata(target)
            if (shape != output_shape or abs(duration - output_duration) > .13
                    or len(post["streams"]) != len(info["streams"])
                    or (stream.get("nb_frames") and video.get("nb_frames") and stream["nb_frames"] != video["nb_frames"])):
                break
            quality = reference_quality(source, target, duration)
            if quality["accepted"]:
                savings = 100 * (1 - target.stat().st_size / size)
                log(f"Cópia de edição {savings:.0f}% menor. {quality['metric'].upper()} mínimo {quality['minimum']}.")
                return target
            break
        except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
            target.unlink(missing_ok=True)
    target.unlink(missing_ok=True)
    log("Pré-compressão preservou a fonte original após o teste de tamanho e qualidade.")
    return source


def compress(path, profile):
    if profile not in PROFILES:
        raise ValueError("Perfil de compressão desconhecido.")
    path = Path(path).resolve(strict=True)
    size = path.stat().st_size
    result = {"profile": profile, "before_bytes": size, "after_bytes": size, "applied": False}
    if profile == "original":
        return result
    codec = "libx264" if profile == "compacto" else "libx265"
    accelerate = runtime.hardware_encoder("hevc", 26) if profile == "hevc" else None
    exe = shutil.which("ffmpeg") if accelerate else available_encoder(codec)
    if not exe:
        return {**result, "reason": f"encoder {codec} indisponível"}
    info, video, stream_shape, duration = metadata(path)
    if sum(s["codec_type"] == "video" for s in info["streams"]) != 1 or video.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
        return {**result, "reason": "fonte HDR ou com múltiplas faixas de vídeo"}
    encoder_args = accelerate or ["-c:v:0", codec, "-preset", "fast", "-crf", "27" if profile == "hevc" else "24"]
    if profile == "hevc":
        if not accelerate:
            encoder_args += ["-x265-params", "pools=2:frame-threads=2"]
        encoder_args += ["-tag:v", "hvc1"]
    with TemporaryDirectory(prefix=".compress-", dir=path.parent) as scratch:
        target = Path(scratch) / path.name
        subprocess.run(runtime.multimedia_args([exe, *FLAGS, "-threads", "2", "-i", str(path), "-map", "0", "-c", "copy",
                        *encoder_args, "-threads:v", "2", "-movflags", "+faststart", str(target)]),
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
