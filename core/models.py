"""Shared data models passed across the contracts (BRIEF.md §4)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Caps:
    """What an engine can produce. ``tags`` drive sensor matching."""
    mesh: bool = False
    brep: bool = False
    ifc: bool = False
    two_d: bool = False
    outputs: tuple[str, ...] = ()       # e.g. ("png", "glb")
    tags: frozenset[str] = frozenset()  # e.g. {"mesh", "render", "image"}


@dataclass
class Brief:
    """A locked design request handed to the loop."""
    text: str
    discovery: dict | None = None


@dataclass
class RunResult:
    """The output of executing a program through a ToolAdapter."""
    code: str
    ok: bool
    renders: list[str] = field(default_factory=list)  # raster paths
    preview: str | None = None                        # web-viewable (.glb)
    exports: dict[str, str] = field(default_factory=dict)  # {"step": path, "ifc": path}
    stdout: str = ""
    error: str | None = None

    @property
    def primary_render(self) -> str | None:
        return self.renders[0] if self.renders else None


@dataclass
class Critique:
    """A Sensor's verdict on a RunResult."""
    score: float
    axis_scores: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    repair_hints: list[str] = field(default_factory=list)
    raw: str = ""
