"""Printability critic (A7) — is this part cleanly 3D-printable for the chosen process?

The critic Ludwig's strongest regime (fabrication) applied to the print3d self-serve wedge. It runs ONLY
when the brief declares a print `process` (fdm/sla), or the print3d pack activates it (A8); otherwise it
is N/A — a precast panel is not printed. Build direction is +Z. Thresholds come from
`standards.yaml: printing` (per process), so a shop tunes them without touching code.

Two gate the export (genuinely unprintable), two advise (printable with care, so they inform but never
block — support and brims are normal print practice, not defects):
  - print_min_wall  [ERROR, gates]     thinnest wall ≥ the process minimum — thinner won't extrude.
  - envelope        [ERROR, gates]     the part fits the printer build volume — bigger won't fit.
  - overhang        [advisory]         steepest downward face vs the support-free limit — else "needs support".
  - bed_contact     [advisory]         first-layer footprint vs the minimum — else "add a brim/raft".

Registered in `critic.panel` with no loop change ([H4]).
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Severity, Status

name = "printability"
applies_to = {"brep"}


def _process(brief) -> str | None:
    return (getattr(brief, "process", None) or "").strip().lower() or None


def evaluate(el, brief) -> Critique:
    from geometry import GeometryService
    from toolkit.standards import printing as _printing

    proc = _process(brief)
    cfg = _printing()
    procs = cfg.get("processes", {}) or {}
    if not proc or proc not in procs:
        return Critique(checks=[CheckResult("printability", Status.NA,
                                            "not a print job (no print process declared)", el.id)])
    p = procs[proc]
    geom = GeometryService()
    checks: list[CheckResult] = []

    # --- min wall (ERROR — walls thinner than the nozzle can lay down won't print) ---
    min_wall = float(p.get("min_wall_mm", 0.8))
    try:
        mw = geom.min_wall_thickness(el.geometry)
        ok = mw >= min_wall - 1e-6
        checks.append(CheckResult(
            "print_min_wall", Status.PASS if ok else Status.FAIL,
            "" if ok else f"min wall {mw:.2f} mm < {min_wall:.2f} mm for {proc}", el.id,
            severity=Severity.ERROR))
    except Exception as e:
        checks.append(CheckResult("print_min_wall", Status.FAIL,
                                  f"min-wall analysis threw: {type(e).__name__}: {e}", el.id,
                                  severity=Severity.ERROR))

    # --- envelope (ERROR — a part bigger than the bed can't be printed whole) ---
    env = cfg.get("envelope_mm")
    if env and len(env) == 3:
        length, width, height = geom.bbox(el.geometry)
        fits = length <= env[0] + 1e-6 and width <= env[1] + 1e-6 and height <= env[2] + 1e-6
        checks.append(CheckResult(
            "envelope", Status.PASS if fits else Status.FAIL,
            "" if fits else (f"part {length:.0f}×{width:.0f}×{height:.0f} exceeds the "
                             f"{env[0]}×{env[1]}×{env[2]} mm build volume"),
            el.id, severity=Severity.ERROR))

    # --- overhang + bed contact (advisory — printable with support/brim; inform, don't block) ---
    stats = geom.print_mesh_stats(el.geometry)
    max_oh = float(p.get("max_overhang_deg", 50))
    oh = stats["max_overhang_deg"]
    checks.append(CheckResult(
        "overhang", Status.PASS,
        (f"max overhang {oh:.0f}° > {max_oh:.0f}° — needs support or a reorient" if oh > max_oh + 1e-6
         else f"max overhang {oh:.0f}° (≤ {max_oh:.0f}° support-free)"),
        el.id, severity=Severity.WARNING))
    min_bed = float(p.get("min_bed_contact_mm2", 100))
    bed = stats["bed_contact_mm2"]
    checks.append(CheckResult(
        "bed_contact", Status.PASS,
        (f"bed contact {bed:.0f} mm² < {min_bed:.0f} mm² — add a brim/raft for adhesion"
         if bed < min_bed - 1e-6 else f"bed contact {bed:.0f} mm²"),
        el.id, severity=Severity.WARNING))

    return Critique(checks=checks)
