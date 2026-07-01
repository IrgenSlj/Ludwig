"""Sketch DoF critic — is the 2D profile behind an extrude actually determined? (R32, the moat.)

A constrained sketch is only a trustworthy parametric part when it is EXACTLY constrained: zero
remaining degrees of freedom and no redundant/conflicting constraints. An under-constrained sketch has
free geometry that a re-solve could move (a silent shape change on edit — the editability thesis's
worst failure); an over-constrained one is redundant at best and unsatisfiable at worst.

This critic reads the constraint state the sketch→extrude compiler recorded ({kind:'sketch'} feature:
dof, solved, redundant) — no re-solve — and reports:
  · unsolved            → ERROR   (conflicting constraints; the profile did not close)
  · redundant (solved)  → ERROR   (over-constrained; dependent constraints)
  · dof > 0             → WARNING  (under-constrained; N free DoF — amber/below-spec in the wash)
  · dof == 0, clean     → PASS     (fully constrained)
NA for any element with no sketch. Registered into the panel without touching the loop ([H4]).
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Severity, Status

name = "sketch"
applies_to = {"brep"}


def evaluate(el, brief) -> Critique:
    el_id = getattr(el, "id", None)
    feat = next((f for f in getattr(el, "features", [])
                 if isinstance(f, dict) and f.get("kind") == "sketch"), None)
    if feat is None:
        return Critique(checks=[CheckResult("sketch_constraints", Status.NA, "no sketch", el_id)])

    dof = int(feat.get("dof", 0))
    solved = bool(feat.get("solved", True))
    redundant = int(feat.get("redundant", 0))
    residual = float(feat.get("residual", 0.0))

    if not solved:
        return Critique(checks=[CheckResult(
            "sketch_constraints", Status.FAIL,
            f"conflicting constraints — the profile did not close (residual {residual:.3g} mm)",
            el_id, severity=Severity.ERROR)])
    if redundant > 0:
        return Critique(checks=[CheckResult(
            "sketch_constraints", Status.FAIL,
            f"over-constrained — {redundant} redundant constraint(s)",
            el_id, severity=Severity.ERROR)])
    if dof > 0:
        return Critique(checks=[CheckResult(
            "sketch_constraints", Status.FAIL,
            f"under-constrained — {dof} degree(s) of freedom remaining",
            el_id, severity=Severity.WARNING)])
    return Critique(checks=[CheckResult(
        "sketch_constraints", Status.PASS, "fully constrained (0 DoF)", el_id)])
