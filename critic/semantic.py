"""Semantic critic — units present, no orphan geometry, declared holes present (BRIEF §6).

Checks design intent rather than raw geometry: every named dim carries a unit, the element actually
owns geometry, and (when the brief declares a hole count) the built part has that many holes — a
proxy for "holes pass through material". Brief is duck-typed (`.holes`); no agent-layer import.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Severity, Status

name = "semantic"
applies_to = {"brep", "ifc"}


def evaluate(el, brief) -> Critique:
    checks: list[CheckResult] = []

    # [H3] Loose elements (crystallization explicitly set > 0 and < 0.5) may skip
    # unit checks — they may not have final params. Default crystallization (0.0)
    # means "not set" and gets full checks.
    loose = 0.0 < el.crystallization < 0.5
    if not loose:
        no_unit = [d.name for d in el.manifest if not getattr(d, "unit", None)]
        checks.append(CheckResult("units_present", Status.PASS if not no_unit else Status.FAIL,
                                  "" if not no_unit else f"named dims without units: {no_unit}", el.id))

    checks.append(CheckResult("has_geometry", Status.PASS if el.geometry is not None else Status.FAIL,
                              "" if el.geometry is not None else "orphan element — no geometry", el.id))

    holes = getattr(brief, "holes", None)
    if holes is not None and el.geometry is not None:
        from geometry import GeometryService
        n = GeometryService().cylindrical_face_count(el.geometry)
        ok = n == holes
        # Loose elements (crystallization explicitly set >0, <0.5): hole count mismatch is a warning, not a failure
        loose = 0.0 < el.crystallization < 0.5
        sev = Severity.WARNING if loose else Severity.ERROR
        checks.append(CheckResult("hole_count", Status.PASS if ok else Status.FAIL,
                                  "" if ok else f"declared {holes} holes, built {n}", el.id,
                                  severity=sev))
    return Critique(checks=checks)
