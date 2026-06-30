"""Compliance critic — Approved Document K stair geometry (BRIEF §6, the verified-fabricability moat).

This is the differentiator: AI-CAD tools emit geometry; Ludwig emits geometry a deterministic critic
has checked against building code. NA for non-Stair elements. For a Stair it reads the use class from
the brief (private / general / institutional) and checks rise / going / pitch / width against the AD-K
limits + 2R+G band in standards.yaml — exact pass/fail, no vision. Registered into the panel without
touching the loop ([H4]); a breach is a WARNING-severity FAIL (amber/below-spec in the Ambient wash).
"""
from __future__ import annotations

import math

from critic.base import CheckResult, Critique, Severity, Status

name = "compliance"
applies_to = {"brep"}


def evaluate(el, brief) -> Critique:
    el_id = getattr(el, "id", None)
    if getattr(el, "type", None) != "Stair":
        return Critique(checks=[CheckResult("stair_compliance", Status.NA, "not a stair", el_id)])

    from toolkit.standards import load
    std = load().get("stairs", {})
    use_class = getattr(brief, "use_class", None) or "general"
    classes = std.get("use_classes", {})
    rule = classes.get(use_class) or classes.get("general") or {}
    band = std.get("two_r_plus_g", [550, 700])

    rise, going, width = el.dim("rise"), el.dim("going"), el.dim("width")
    if rise is None or going is None:
        return Critique(checks=[CheckResult("stair_compliance", Status.NA,
                                            "stair has no rise/going dims", el_id)])

    checks: list[CheckResult] = []

    def chk(check_name: str, ok: bool, msg: str) -> None:
        checks.append(CheckResult(check_name, Status.PASS if ok else Status.FAIL,
                                  "" if ok else msg, el_id, severity=Severity.WARNING))

    pitch = math.degrees(math.atan2(rise, going))
    two_rg = 2 * rise + going
    rmax, gmin, pmax, wmin = (rule.get("rise_max"), rule.get("going_min"),
                              rule.get("pitch_max"), rule.get("width_min"))
    uc = use_class
    if rmax is not None:
        chk("rise", rise <= rmax + 1e-6, f"rise {rise:.0f} > {rmax:.0f} mm max ({uc})")
    if gmin is not None:
        chk("going", going >= gmin - 1e-6, f"going {going:.0f} < {gmin:.0f} mm min ({uc})")
    if pmax is not None:
        chk("pitch", pitch <= pmax + 1e-6, f"pitch {pitch:.1f}° > {pmax:.0f}° max ({uc})")
    chk("2R+G", band[0] <= two_rg <= band[1], f"2R+G {two_rg:.0f} outside {band[0]}–{band[1]} mm")
    if wmin is not None and width is not None:
        chk("width", width >= wmin - 1e-6, f"width {width:.0f} < {wmin:.0f} mm min ({uc})")
    return Critique(checks=checks)
