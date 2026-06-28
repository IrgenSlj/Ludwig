"""Manufacturing critic — cast-in anchor cover (edge clearance) on panels (BRIEF §6).

Checks that every registered anchor feature has at least `cover_mm` of concrete between
the anchor bore and the nearest panel face. Heavy imports (geometry kernel, standards) are lazy.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Severity, Status

name = "manufacturing"
applies_to = {"brep"}


def evaluate(el, brief) -> Critique:  # noqa: ARG001 - brief unused for manufacturing checks
    features = getattr(el, "features", [])
    anchors = [f for f in features if f.get("kind") == "anchor"]

    if not anchors:
        return Critique(checks=[CheckResult("cover", Status.NA, "no cast-in features", el.id)])

    from geometry import GeometryService
    from toolkit.standards import cover_mm

    length, thickness, _height = GeometryService().bbox(el.geometry)
    cov = cover_mm()
    checks: list[CheckResult] = []
    for i, a in enumerate(anchors, 1):
        x, y = a["at"]
        r = a["diameter"] / 2
        edge = min(length / 2 - abs(x) - r, thickness / 2 - abs(y) - r)
        ok = edge >= cov
        checks.append(CheckResult(
            f"cover:anchor_{i}",
            Status.PASS if ok else Status.FAIL,
            "" if ok else f"edge clearance {edge:.1f} mm < cover {cov:.0f} mm",
            el.id, severity=Severity.WARNING))
    return Critique(checks=checks)
