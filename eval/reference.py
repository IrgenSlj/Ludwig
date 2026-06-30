"""Deterministic REFERENCE builder for the frozen brief set.

It is the oracle that proves the pass-rate harness is wired correctly: a hand-written, known-correct
program per brief. In P0/S3 the LLM codegen builder replaces this — and the harness then reports the
real `first-pass geometric pass-rate` ([H6]) instead of the trivial 100% a correct oracle yields.
"""
from __future__ import annotations

from toolkit import anchor, assembly, box, clearance_hole, hole, panel, part, profile, stack, stair
from ir.elements import BRepHandle, Element


def build(brief: dict) -> Element:
    bid, d = brief["id"], brief["dims"]
    if bid == "precast_panel":
        el = panel(bid, d["length"], d["height"], d["thickness"])  # length, height, thickness
        anchor(el, 17.5, (-750, 0), 150)  # two M16 cast-in lifting anchors (⌀17.5), 150mm deep
        anchor(el, 17.5, (750, 0), 150)
        return el
    if bid == "stacked_plates":
        base = box("base", 60, 60, 10)
        top = box("top", 40, 40, 10)
        stack(base, top)  # seat top on base's +z face → union 60×60×20
        return assembly(bid, base, top)
    # ---- P0/S3 expansion: harder cases ----
    if bid == "filtered_bracket":
        return _filtered_bracket(brief)
    if bid == "slotted_plate":
        return _slotted_plate(brief)
    if bid == "chamfered_spacer":
        return _chamfered_spacer(brief)
    if bid == "asymmetric_gusset":
        return _asymmetric_gusset(brief)
    if bid == "counterbored_plate":
        return _counterbored_plate(brief)
    if bid == "steel_beam":
        return _steel_beam(brief)
    if bid == "stair_flight":
        s = brief.get("stair", {})
        return stair(bid, rise=s.get("rise", 170), going=s.get("going", 280),
                     width=s.get("width", 1000), riser_count=s.get("riser_count", 17))
    # ---- original simple builders ----
    el = box(bid, d["length"], d["width"], d["height"])
    if bid == "bracket":
        clearance_hole(el, "M8", (-25, 0))
        clearance_hole(el, "M8", (25, 0))
    elif bid == "spacer":
        hole(el, 10.0, (0, 0))
    elif bid == "flat_bar":
        for x in (-75, -25, 25, 75):
            clearance_hole(el, "M6", (x, 0))
    elif bid == "gusset":
        clearance_hole(el, "M10", (-30, 0))
        clearance_hole(el, "M10", (30, 0))
    # "plate" has no holes
    return el


# ---------------------------------------------------------------------------
# P0/S3 expansion — reference oracles for the 5 new briefs
# ---------------------------------------------------------------------------

def _filtered_bracket(brief):
    """80×40×6 bracket, 5mm fillet on all 4 top edges, 2× M8 clearance holes."""
    el = part("filtered_bracket")
    length, width, height = 80.0, 40.0, 6.0

    def build():
        import cadquery as cq
        return (cq.Workplane("XY")
                .box(length, width, height)
                .faces(">Z").fillet(5.0))

    el.geometry = BRepHandle(build)
    el.register_dim("length", length)
    el.register_dim("width", width)
    el.register_dim("height", height)
    clearance_hole(el, "M8", (-25, 0))
    clearance_hole(el, "M8", (25, 0))
    return el


def _slotted_plate(brief):
    """120×60×10 plate with a 40×10 rectangular through slot at centre."""
    el = part("slotted_plate")
    length, width, height = 120.0, 60.0, 10.0

    def build():
        import cadquery as cq
        return (cq.Workplane("XY")
                .box(length, width, height)
                .faces(">Z").workplane()
                .rect(40, 10).cutThruAll())

    el.geometry = BRepHandle(build)
    el.register_dim("length", length)
    el.register_dim("width", width)
    el.register_dim("height", height)
    return el


def _chamfered_spacer(brief):
    """30×30×12 spacer with a ⌀10 bore and 2mm chamfer on both bore edges."""
    el = part("chamfered_spacer")
    length, width, height = 30.0, 30.0, 12.0

    def build():
        import cadquery as cq
        wp = cq.Workplane("XY").box(length, width, height)
        wp = wp.faces(">Z").workplane().hole(10.0)
        wp = wp.edges("%Circle").chamfer(2.0)
        return wp

    el.geometry = BRepHandle(build)
    el.register_dim("length", length)
    el.register_dim("width", width)
    el.register_dim("height", height)
    return el


def _asymmetric_gusset(brief):
    """100×100×5 gusset, two M10 holes at (20,15) and (-30,25)."""
    el = box("asymmetric_gusset", 100, 100, 5)
    clearance_hole(el, "M10", (20, 15))
    clearance_hole(el, "M10", (-30, 25))
    return el


def _steel_beam(brief):
    """2000 mm long, 100 × 50 mm cross-section — a Profile element."""
    d = brief["dims"]
    return profile(brief["id"], d["length"], d["width"], d["height"])


def _counterbored_plate(brief):
    """80×50×10 plate, two M6 counterbored holes (⌀6.6 through, ⌀11 cbore 5mm deep)."""
    el = part("counterbored_plate")
    length, width, height = 80.0, 50.0, 10.0

    def build():
        import cadquery as cq
        wp = cq.Workplane("XY").box(length, width, height)
        for x, y in [(-20, 0), (20, 0)]:
            # Through hole: M6 clearance (⌀6.6)
            th = (cq.Workplane("XY")
                  .transformed(offset=(x, y, -height / 2))
                  .circle(3.3).extrude(height))
            wp = wp.cut(th)
            # Counterbore: ⌀11, 5mm deep from the top face
            cb = (cq.Workplane("XY")
                  .transformed(offset=(x, y, height / 2))
                  .circle(5.5).extrude(-5))
            wp = wp.cut(cb)
        return wp

    el.geometry = BRepHandle(build)
    el.register_dim("length", length)
    el.register_dim("width", width)
    el.register_dim("height", height)
    return el
