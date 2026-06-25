"""STEP backend — the fabrication deliverable (BRIEF §7, P0/S5).

A FABRICATION export: gated behind explicit confirmation, and a pre-export validation hook runs
the deterministic critic first (BRIEF §5, last line of defense). CadQuery/OCCT imported lazily.
Gate: the bracket's STEP opens in FreeCAD with correct geometry.
"""
from __future__ import annotations

from pathlib import Path

name = "step"
fmt = "step"
fabrication = True


def compile(ir: object, out_dir: Path) -> Path:  # noqa: A001, ARG001
    raise NotImplementedError("step.compile — P0/S5")
