"""Backend contract — backends are DERIVED projections of the IR, never authored (BRIEF §2.4).

Adding a backend must not modify the loop (BRIEF §0 gate). STEP/IFC/drawing/render/present all
implement this. Representation-switching in the UI is real only because these are true projections
of one IR (docs/UX_BRIEF.md).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

_UNSAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")


def artifact_stem(ir_id: object) -> str:
    """The filename stem for an IR element's artifacts — sanitised, never the raw id.

    An element id is authored data: it comes from the Op-API (`AddElement.id`, client-supplied) or
    from a model-written recipe. Every backend names its output `<id>.<fmt>`, so an id of `../x` or
    `/etc/x` would write the artifact OUTSIDE `out_dir`. Backends emit fabrication files — that write
    must stay inside the directory the caller named, whatever the id says.

    Keeps `[A-Za-z0-9._-]`, folds anything else to `_`, and refuses a stem that is empty or would
    address a parent (`.`, `..`, or a leading dot).
    """
    stem = _UNSAFE_STEM.sub("_", str(ir_id)).strip("._-")
    return stem[:96] if stem else "element"


@runtime_checkable
class Backend(Protocol):
    name: str            # "step", "ifc", "drawing", "render", "present"
    fmt: str             # output extension, e.g. "step", "ifc", "svg", "png", "pptx"
    fabrication: bool    # True → export is gated behind explicit confirmation (BRIEF §5 permissions)

    def compile(self, ir: object, out_dir: Path) -> Path:
        """Project the IR to this backend's artifact; return the written path."""
        ...
