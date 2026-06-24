"""The two contracts everything plugs into (BRIEF.md §4).

``ToolAdapter`` — one per creative engine (Blender today; CadQuery/IFC later).
``Sensor``      — one per evaluation modality (vision today; geometry/IFC later).

The orchestrator never knows which concrete engines or sensors exist; it asks the
registry. Adding one is implementing a protocol and registering it — no loop change.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import Brief, Caps, Critique, RunResult


@runtime_checkable
class ToolAdapter(Protocol):
    name: str       # "blender", "cadquery", "ifc"
    language: str   # the language the agent writes programs in

    def capabilities(self) -> Caps: ...

    def toolkit_reference(self) -> str:
        """Helper/toolkit docs injected into the codegen prompt."""
        ...

    def run(self, program: str, project_dir: Path) -> RunResult:
        """Execute the agent-written program; emit renders / preview / exports."""
        ...

    def preview(self, result: RunResult) -> str | None:
        """Path to a web-viewable preview (.glb), if any."""
        ...


@runtime_checkable
class Sensor(Protocol):
    name: str
    applies_to: set[str]   # capability tags this sensor can judge

    def evaluate(self, result: RunResult, brief: Brief) -> Critique: ...
