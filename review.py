"""Export source cuts and layout notes as an editable OpenTimelineIO timeline."""
import argparse
import json
from pathlib import Path


def export_review(source, shots, destination, audio=True):
    import opentimelineio as otio

    rate = 30
    timeline = otio.schema.Timeline(
        name=destination.stem, metadata={"ClipStudio": {"aspect_ratio": "9:16", "review_only": True}})
    kinds = [otio.schema.TrackKind.Video]
    if audio:
        kinds.append(otio.schema.TrackKind.Audio)
    elapsed = 0.
    frames = []
    for start, end, _ in shots:
        first = round(elapsed * rate)
        elapsed += end - start
        frames.append(max(1, round(elapsed * rate) - first))
    for kind in kinds:
        track = otio.schema.Track(name=kind, kind=kind)
        for (start, end, style), count in zip(shots, frames):
            clip = otio.schema.Clip(
                name=f"{source.stem} / {style}",
                media_reference=otio.schema.ExternalReference(target_url=source.resolve().as_uri()),
                source_range=otio.opentime.TimeRange(
                    otio.opentime.RationalTime(round(start * rate), rate),
                    otio.opentime.RationalTime(count, rate)),
                metadata={"ClipStudio": {"layout_hint": style, "source_start": start, "source_end": end}},
            )
            track.append(clip)
        timeline.tracks.append(track)
    otio.adapters.write_to_file(timeline, str(destination))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--clip", type=int, default=1)
    parser.add_argument("--style", default="")
    args = parser.parse_args()
    data = json.loads(args.plan.read_text(encoding="utf-8"))
    if "source_ranges" in data:
        shots = data["source_ranges"]
    else:
        try:
            if args.clip < 1:
                raise IndexError
            entry = data["clips"][args.clip - 1]
            layout = entry["variants"][args.style]["layouts"] if args.style else entry["layouts"]
            shots = [(row["start"], row["end"], row["style"]) for row in layout]
        except (IndexError, KeyError):
            parser.error("Clipe ou estilo ausente no plano.")
    source = Path(data["source"])
    if not source.is_file() or args.out.suffix.lower() != ".otio" or args.out.exists():
        parser.error("A mídia de origem precisa existir e o destino .otio deve ser novo.")
    from engine import probe
    export_review(source, shots, args.out, probe(source)[1])


if __name__ == "__main__":
    main()
