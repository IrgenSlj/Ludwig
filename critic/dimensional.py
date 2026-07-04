"""Dimensional critic — every named dim in the brief is present and EXACT (BRIEF §6).

The low-noise heart of the moat: the signal the mesh-era vision critic never had (docs/FINDINGS.md).
Each declared dim is checked to `tolerances.linear` (1e-6) against, in order:
  1. an axis-aligned bbox EXTENT measured from the built geometry — ground truth. length/width/height map
     to x/y/z; `thickness` maps to the middle (y) extent and `diameter` to the radial (x) extent, so a
     panel's thickness and a cylinder's diameter are verified against the SOLID, not just their own
     registered value (matches the eval harness's extent map);
  2. otherwise a value the program REGISTERED into the manifest via `register_dim` (a hole spacing, a
     non-extent size) — the seam `prompts/codegen.md` requires codegen to fill.
Without (2), `register_dim` had zero effect on the verdict and any non-extent named dim was unverifiable.
Reads the brief by duck-typing (`.named_dims`) so the critic never imports the agent layer.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Status

name = "dimensional"
applies_to = {"brep"}


def evaluate(el, brief) -> Critique:
    from geometry import GeometryService
    from toolkit.standards import tol_linear, bbox_gate

    # [H3] Crystallization gates dimensional strictness.
    # Loose elements (crystallization explicitly set > 0 and < 0.5) use the wider
    # bbox_gate tolerance and only check extent dims. Default crystallization (0.0)
    # means "not set" — full strict checks. Locked elements (>= 0.5) also get full strictness.
    loose = 0.0 < el.crystallization < 0.5
    tol = bbox_gate() if loose else tol_linear()

    declared = dict(getattr(brief, "named_dims", {}) or {})
    if not declared:
        # No brief-declared dims (a gallery seed, an adopt/verify path, a bare compile). Fall back to
        # self-verifying the element's OWN registered EXTENT dims against the measured solid — so every
        # part gets real dimensional coverage instead of a vacuous n/a (the headline check the demo is
        # meant to prove), and any op that desyncs a registered extent from geometry is caught. Includes
        # `thickness` (panels) and `diameter` (cylinders) — both bbox-measurable (see `extents` below).
        declared = {k: el.dim(k) for k in ("length", "width", "height", "thickness", "diameter")
                    if el.dim(k) is not None}
        if not declared:
            return Critique(checks=[CheckResult("dimensional", Status.NA,
                                                "no declared or registered extent dims", el.id)])

    g = GeometryService()
    length, width, height = g.bbox(el.geometry)
    # `thickness`→middle (y) extent, `diameter`→radial (x) extent — a panel/cylinder's defining size is
    # then checked against the SOLID, not merely its own registered value (same map as eval/harness.py).
    extents = {"length": length, "width": width, "height": height,
               "thickness": width, "diameter": length}
    checks: list[CheckResult] = []
    for dim_name, want in declared.items():
        # Ground truth first (measured extent), then the registered manifest value.
        have = extents.get(dim_name)
        if have is None:
            have = el.dim(dim_name)
            if loose and have is None:
                # Loose element: skip non-extent dims that aren't registered
                continue
        ok = have is not None and abs(have - want) <= tol
        checks.append(CheckResult(
            f"dim:{dim_name}", Status.PASS if ok else Status.FAIL,
            "" if ok else (f"declared {want} mm, built {have:.4f} mm" if have is not None
                           else f"declared {want} mm — not an axis-aligned extent and not registered"),
            el.id))
    return Critique(checks=checks)
