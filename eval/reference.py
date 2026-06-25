"""Deterministic REFERENCE builder for the frozen brief set.

It is the oracle that proves the pass-rate harness is wired correctly: a hand-written, known-correct
program per brief. In P0/S3 the LLM codegen builder replaces this — and the harness then reports the
real `first-pass geometric pass-rate` ([H6]) instead of the trivial 100% a correct oracle yields.
"""
from __future__ import annotations

from toolkit import anchor, box, clearance_hole, hole, panel
from ir.elements import Element


def build(brief: dict) -> Element:
    bid, d = brief["id"], brief["dims"]
    if bid == "precast_panel":
        el = panel(bid, d["length"], d["height"], d["width"])  # length, height, thickness(=width)
        anchor(el, 17.5, (-750, 0), 150)  # two M16 cast-in lifting anchors (⌀17.5), 150mm deep
        anchor(el, 17.5, (750, 0), 150)
        return el
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
