"""STEP backend — the fabrication deliverable (BRIEF §7, P0/S5).

The first artifact a user *keeps*: an exact OCCT B-rep written to a `.step` file any CAD tool opens.
A FABRICATION export (`fabrication = True`) — the app layer gates it behind confirmation, and a
pre-export validation hook runs the critic first (BRIEF §5). CadQuery/OCCT imported lazily.
"""
from __future__ import annotations

from pathlib import Path

name = "step"
fmt = "step"
fabrication = True


def compile(ir, out_dir) -> Path:  # noqa: A001 - matches the Backend protocol
    """Project the element's solid to a STEP file in out_dir; return the path."""
    import cadquery as cq

    if ir.geometry is None:
        raise ValueError(f"element {ir.id!r} has no geometry to export")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.step"
    cq.exporters.export(ir.geometry.solid(), str(path), exportType="STEP")
    return path


def reimport_bbox(path) -> tuple[float, float, float]:
    """Round-trip helper: re-read a STEP through OCCT (the kernel FreeCAD/CAD tools use) and
    return its bbox — proves the written file is valid, openable geometry, not just bytes."""
    import cadquery as cq

    bb = cq.importers.importStep(str(path)).val().BoundingBox()
    return (bb.xlen, bb.ylen, bb.zlen)
