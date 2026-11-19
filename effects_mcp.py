"""MCP server for the local Clip Studio bank. Transport: stdio."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from effects_bank import catalog, new_preview, preview_transition, render_cues

server = FastMCP("clip-studio-effects")


class CatalogResult(BaseModel):
    origin: str
    sounds: dict[str, str]
    transitions: dict[str, dict[str, str | bool | None]]


class SoundResult(BaseModel):
    path: str
    peak_db: int


class TransitionResult(BaseModel):
    path: str
    transition: str


@server.tool()
def list_effects() -> CatalogResult:
    """List local synthesized sounds and editable transition recipes."""
    return CatalogResult(**catalog())


@server.tool()
def render_sound(name: Literal["whoosh", "radio", "impacto", "resolucao"], peak_db: int = -8) -> SoundResult:
    """Synthesize a short WAV inside the project's preview folder. No external media."""
    if not -24 <= peak_db <= -3:
        raise ValueError("peak_db must be between -24 and -3.")
    return SoundResult(path=str(render_cues(new_preview(".wav"), .3, [(0, name)], peak_db)), peak_db=peak_db)


@server.tool()
def render_transition(name: Literal["corte", "linha", "zoom", "dissolve", "slide", "wipe"]) -> TransitionResult:
    """Preview a transition on synthetic color patterns inside the project."""
    return TransitionResult(path=str(preview_transition(name)), transition=name)


class V9ReferenceResult(BaseModel):
    name: str
    fps: int
    beat: dict | None = None
    reference: dict | None = None


def _v9_recipe():
    path = (Path(__file__).resolve().parent / ".agents" / "skills"
            / "alanzoka-v9-reference" / "references" / "v9.json")
    return json.loads(path.read_text(encoding="utf-8"))


@server.tool()
def get_v9_reference(second: float | None = None) -> V9ReferenceResult:
    """Get the Alanzoka V9 recipe or a timeline beat at a specific second."""
    reference = _v9_recipe()
    if second is None:
        return V9ReferenceResult(name=reference["name"], fps=reference["fps"], reference=reference)
    if not 0 <= second < reference["duration_seconds"]:
        raise ValueError("O segundo deve estar entre 0 e 14,5, antes do fim.")
    beat = next(beat for beat in reference["beats"] if beat["second"] <= second < beat["until"])
    return V9ReferenceResult(name=reference["name"], fps=reference["fps"], beat=beat)


@server.tool()
def render_v9_accent() -> TransitionResult:
    """Preview the V9 five-frame dissolve and leading impact on synthetic images."""
    from engine import FF, command, encoder

    reference = _v9_recipe()
    fps = reference["fps"]
    fade = reference["transitions"]["dissolve"]
    impact = next(cue for cue in reference["audio"]["cues"] if cue["name"] == "impacto")
    preview_cut = 1.2
    lead = fade["seconds"] - impact["seconds"]
    target = new_preview(".mp4")
    with TemporaryDirectory(prefix="v9-accent-", dir=target.parent) as work:
        sound = Path(work) / "impact.wav"
        partial = Path(work) / "preview.mp4"
        render_cues(sound, 2.7, [(preview_cut - lead, "impacto")], impact["isolated_peak_dbfs"])
        graph = (f"[0:v][1:v]xfade=transition=fade:duration={fade['duration_frames'] / fps:.6f}"
                 f":offset={preview_cut}[out]")
        command(FF + ["-y", "-f", "lavfi", "-i", f"testsrc2=s=360x640:r={fps}:d=1.6",
                      "-f", "lavfi", "-i", f"smptebars=s=360x640:r={fps}:d=1.5",
                      "-i", str(sound), "-filter_complex_threads", "1", "-filter_complex", graph,
                      "-map", "[out]", "-map", "2:a:0", "-pix_fmt", "yuv420p", "-c:a", "aac",
                      "-movflags", "+faststart", "-t", "2.7", *encoder(), str(partial)])
        partial.replace(target)
    return TransitionResult(path=str(target), transition="dissolve_v9")


if __name__ == "__main__":
    server.run(transport="stdio")
