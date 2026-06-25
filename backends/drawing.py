"""Drawing backend — OCCT HLR → SVG + ezdxf DXF, dims queried from the manifest (BRIEF §7, P0.5/S7).

Deliberately OUTSIDE the P0 spine gate: OCCT HLR is fragile (open correctness bugs, perf cliffs),
so it must not block proving the solid spine. Provide an exact↔polygonal HLR toggle
(standards.yaml `drawing.hlr_algorithm`). Conventioned architectural drawings (poché, swings,
dimension strings) are the much harder P2 problem — the real moat.
"""
from __future__ import annotations

from pathlib import Path

name = "drawing"
fmt = "svg"
fabrication = False


def compile(ir: object, out_dir: Path) -> Path:  # noqa: A001, ARG001
    raise NotImplementedError("drawing.compile — P0.5/S7")
