"""Manufacturing critic — cast-in anchor cover + min-wall analysis (BRIEF §6 / P1).

Checks:
- [cover] every registered anchor feature has at least `cover_mm` of concrete between
  the anchor bore and the nearest panel face.
- [min_wall] minimum wall thickness >= min_wall_mm (standards.yaml), computed via
  OCCT face-pair distance (research-grade; a full medial-surface / offset analysis is P2).

Heavy imports (geometry kernel, standards) are lazy.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Severity, Status

name = "manufacturing"
applies_to = {"brep"}


def evaluate(el, brief) -> Critique:  # noqa: ARG001 - brief unused for manufacturing checks
    from geometry import GeometryService
    from toolkit.standards import cover_mm as _cover_mm, load

    geom = GeometryService()
    features = getattr(el, "features", [])
    anchors = [f for f in features if f.get("kind") == "anchor"]
    std = load()
    checks: list[CheckResult] = []

    # ---- anchor cover (edge clearance) ----
    if not anchors:
        checks.append(CheckResult("cover", Status.NA, "no cast-in features", el.id))
    else:
        length, thickness, _height = geom.bbox(el.geometry)
        cov = _cover_mm()
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

    # ---- min-wall analysis ----
    min_wall_mm = std.get("manufacturing", {}).get("min_wall_mm", 1.5)
    try:
        mw = geom.min_wall_thickness(el.geometry)
        ok = mw >= min_wall_mm - 1e-6
        checks.append(CheckResult(
            "min_wall",
            Status.PASS if ok else Status.FAIL,
            "" if ok else f"min wall thickness {mw:.3f} mm < {min_wall_mm:.1f} mm",
            el.id, severity=Severity.WARNING))
    except Exception as e:
        checks.append(CheckResult(
            "min_wall", Status.FAIL,
            f"min-wall analysis threw: {type(e).__name__}: {e}",
            el.id, severity=Severity.ERROR))

    return Critique(checks=checks)
