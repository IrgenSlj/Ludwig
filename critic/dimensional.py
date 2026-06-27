"""Dimensional critic — every named dim in the brief is present and EXACT (BRIEF §6).

The low-noise heart of the moat: the signal the mesh-era vision critic never had (docs/FINDINGS.md).
Each declared dim is checked to `tolerances.linear` (1e-6) against, in order:
  1. an axis-aligned bbox EXTENT (length/width/height) measured from the built geometry — ground truth;
  2. otherwise a value the program REGISTERED into the manifest via `register_dim` (a bore diameter,
     a panel thickness, a hole spacing) — the seam `prompts/codegen.md` requires codegen to fill.
Without (2), `register_dim` had zero effect on the verdict and any non-extent named dim was unverifiable.
Reads the brief by duck-typing (`.named_dims`) so the critic never imports the agent layer.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Status

name = "dimensional"
applies_to = {"brep"}


def evaluate(el, brief) -> Critique:
    from geometry import GeometryService
    from toolkit.standards import tol_linear

    declared = dict(getattr(brief, "named_dims", {}) or {})
    if not declared:
        return Critique(checks=[CheckResult("dimensional", Status.NA, "no declared dims", el.id)])

    g = GeometryService()
    length, width, height = g.bbox(el.geometry)
    extents = {"length": length, "width": width, "height": height}
    tol = tol_linear()
    checks: list[CheckResult] = []
    for dim_name, want in declared.items():
        # Ground truth first (measured extent), then the registered manifest value.
        have = extents.get(dim_name)
        if have is None:
            have = el.dim(dim_name)
        ok = have is not None and abs(have - want) <= tol
        checks.append(CheckResult(
            f"dim:{dim_name}", Status.PASS if ok else Status.FAIL,
            "" if ok else (f"declared {want} mm, built {have:.4f} mm" if have is not None
                           else f"declared {want} mm — not an axis-aligned extent and not registered"),
            el.id))
    return Critique(checks=checks)
