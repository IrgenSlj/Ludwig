"""STL backend (A7) — the mesh a slicer eats.

The fabrication deliverable for 3D printing: the exact OCCT B-rep tessellated to a watertight `.stl`
any slicer (Cura, PrusaSlicer, Bambu) opens. A FABRICATION export — gated behind the critic exactly
like STEP, so a part that fails the printability critic never leaves as an STL. Tessellation deflection
reads optional printing.stl keys from the loaded standards (falls back to sane defaults). CadQuery/OCCT imported lazily.
"""
from __future__ import annotations

from pathlib import Path

name = "stl"
fmt = "stl"
fabrication = True


def _deflection() -> tuple[float, float]:
    """(linear mm, angular rad) tessellation tolerance for the STL — finer than the viewport mesh so
    curves print smooth. From `printing.stl` if set, else a 0.05 mm / 0.3 rad default."""
    try:
        from toolkit.standards import printing
        stl = (printing().get("stl") or {})
        return float(stl.get("linear_deflection_mm", 0.05)), float(stl.get("angular_deflection_rad", 0.3))
    except Exception:
        return 0.05, 0.3


def compile(ir, out_dir) -> Path:  # noqa: A001 - matches the Backend protocol
    """Tessellate the element's solid to an STL in out_dir; return the path."""
    import cadquery as cq

    if ir.geometry is None:
        raise ValueError(f"element {ir.id!r} has no geometry to export")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ir.id}.stl"
    lin, ang = _deflection()
    cq.exporters.export(ir.geometry.solid(), str(path), exportType="STL",
                        tolerance=lin, angularTolerance=ang)
    return path


# Module-level self-registration
from backends.registry import register as _register
import sys as _sys
_register(_sys.modules[__name__])
