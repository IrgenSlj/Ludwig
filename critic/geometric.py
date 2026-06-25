"""Geometric critic (OCCT) — manifold, watertight, no self-intersection (BRIEF §6).

OCCT's `BRepCheck_Analyzer` (exposed as cq Shape.isValid) is the real manifold/self-intersection
check, so it is honest signal, not a heuristic. min-wall is a P0 heuristic and NEVER a P0 gate
(OCCT booleans throw StdFail_NotDone exactly there; real thickness analysis is P1). Heavy import lazy.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Status

name = "geometric"
applies_to = {"brep"}


def evaluate(el, brief) -> Critique:  # noqa: ARG001 - brief unused for geometric checks
    from geometry import GeometryService

    g = GeometryService()
    if el.geometry is None:
        return Critique(checks=[CheckResult("watertight_manifold", Status.FAIL,
                                            "element has no geometry", el.id)])
    try:
        valid = g.is_valid(el.geometry)
    except Exception as e:  # a build that throws is a hard geometric failure (StdFail_NotDone &c.)
        return Critique(checks=[CheckResult("watertight_manifold", Status.FAIL,
                                            f"geometry build failed: {type(e).__name__}: {e}", el.id)])
    return Critique(checks=[CheckResult(
        "watertight_manifold", Status.PASS if valid else Status.FAIL,
        "" if valid else "OCCT reports the solid invalid (non-manifold / not watertight / self-intersecting)",
        el.id)])
