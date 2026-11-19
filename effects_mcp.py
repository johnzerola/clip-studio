"""MCP server for the local Clip Studio bank. Transport: stdio."""
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


if __name__ == "__main__":
    server.run(transport="stdio")
