"""Handoff a finished vertical clip to a separate MakeMyClip review workspace."""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def make_plan(source):
    return {"schema": 1, "source": str(source.resolve()), "mode": "review_rendered_clip",
            "argv": [["timeline", "new", "--width", "720", "--height", "1280"],
                     ["timeline", "add-media", str(source.resolve())],
                     ["timeline", "check", "--sheet", "cortes.jpg"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--node-entry", type=Path,
                        help="Arquivo JS da CLI MakeMyClip já instalada; sem isso, só exporta o plano.")
    args = parser.parse_args()
    if not args.source.is_file() or args.workspace.exists():
        parser.error("Informe um MP4 existente e uma pasta de revisão nova.")
    node = shutil.which("node")
    ffmpeg = shutil.which("ffmpeg")
    if args.node_entry and (not args.node_entry.is_file() or not node or not ffmpeg):
        parser.error("A execução precisa do Node, do FFmpeg e do arquivo JS da CLI.")
    args.workspace.mkdir(parents=True)
    plan = make_plan(args.source)
    path = args.workspace / "makemyclip-plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.node_entry:
        env = dict(os.environ, MAKEMYCLIP_WORKSPACE=str(args.workspace.resolve()),
                   MAKEMYCLIP_FFMPEG_PATH=ffmpeg)
        for argv in plan["argv"]:
            subprocess.run([node, str(args.node_entry.resolve()), *argv],
                           cwd=args.workspace, env=env, check=True, timeout=180)
    print(path)


if __name__ == "__main__":
    main()
