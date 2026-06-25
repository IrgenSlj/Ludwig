"""Backend contract — backends are DERIVED projections of the IR, never authored (BRIEF §2.4).

Adding a backend must not modify the loop (BRIEF §0 gate). STEP/IFC/drawing/render/present all
implement this. Representation-switching in the UI is real only because these are true projections
of one IR (docs/UX_BRIEF.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Backend(Protocol):
    name: str            # "step", "ifc", "drawing", "render", "present"
    fmt: str             # output extension, e.g. "step", "ifc", "svg", "png", "pptx"
    fabrication: bool    # True → export is gated behind explicit confirmation (BRIEF §5 permissions)

    def compile(self, ir: object, out_dir: Path) -> Path:
        """Project the IR to this backend's artifact; return the written path."""
        ...
