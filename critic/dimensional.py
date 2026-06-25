"""Dimensional critic — every named dim in the brief is present and EXACT (BRIEF §6).

The low-noise heart of the moat: the signal the mesh-era vision critic never had (docs/FINDINGS.md).
Checks the built bounding box against the brief's declared dims to `tolerances.linear` (1e-6).
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
    built = {"length": length, "width": width, "height": height}
    tol = tol_linear()
    checks: list[CheckResult] = []
    for dim_name, want in declared.items():
        have = built.get(dim_name)
        ok = have is not None and abs(have - want) <= tol
        checks.append(CheckResult(
            f"dim:{dim_name}", Status.PASS if ok else Status.FAIL,
            "" if ok else (f"declared {want} mm, built {have:.4f} mm" if have is not None
                           else f"declared {want} mm, not an axis-aligned extent"),
            el.id))
    return Critique(checks=checks)
