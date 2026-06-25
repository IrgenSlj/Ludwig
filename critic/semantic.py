"""Semantic critic — units present, no orphan geometry, declared holes present (BRIEF §6).

Checks design intent rather than raw geometry: every named dim carries a unit, the element actually
owns geometry, and (when the brief declares a hole count) the built part has that many holes — a
proxy for "holes pass through material". Brief is duck-typed (`.holes`); no agent-layer import.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Status

name = "semantic"
applies_to = {"brep", "ifc"}


def evaluate(el, brief) -> Critique:
    checks: list[CheckResult] = []

    no_unit = [d.name for d in el.manifest if not getattr(d, "unit", None)]
    checks.append(CheckResult("units_present", Status.PASS if not no_unit else Status.FAIL,
                              "" if not no_unit else f"named dims without units: {no_unit}", el.id))

    checks.append(CheckResult("has_geometry", Status.PASS if el.geometry is not None else Status.FAIL,
                              "" if el.geometry is not None else "orphan element — no geometry", el.id))

    holes = getattr(brief, "holes", None)
    if holes is not None and el.geometry is not None:
        from geometry import GeometryService
        n = GeometryService().cylindrical_face_count(el.geometry)
        checks.append(CheckResult("hole_count", Status.PASS if n == holes else Status.FAIL,
                                  "" if n == holes else f"declared {holes} holes, built {n}", el.id))
    return Critique(checks=checks)
