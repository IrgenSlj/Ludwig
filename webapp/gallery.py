"""Trusted seed parts for the public demo — server-side programs, never client-supplied.

The free public demo runs in DEMO mode (env LUDWIG_DEMO=1). The browser never sends a fresh program
string to execute (that would be remote code execution — and BRIEF §10 forbids running untrusted code
in a tool that emits fabrication files). Instead it picks a seed by id; the server holds the trusted
parametric program, and only NUMERIC parameter edits are permitted (validated in webapp/safety.py).

Each seed is a real Ludwig program (raw toolkit calls). Loading + dragging dimensions + deriving
STEP/IFC/DXF runs entirely through the deterministic, no-LLM core — zero inference cost per visitor.
"""
from __future__ import annotations

# Curated so a visitor immediately has real, manipulable B-rep across the beachhead: a fastener-style
# bracket, plate/bar/spacer stock, a structural gusset, a precast panel (BIM), and an assembly.
SEEDS = [
    {"id": "bracket", "title": "Steel bracket", "blurb": "80 × 40 × 6 mm · two M8 clearance holes",
     "program": ('element = box("bracket", 80, 40, 6)\n'
                 'clearance_hole(element, "M8", (-25, 0))\n'
                 'clearance_hole(element, "M8", (25, 0))\n')},
    {"id": "plate", "title": "Flat plate", "blurb": "120 × 60 × 10 mm",
     "program": 'element = box("plate", 120, 60, 10)\n'},
    {"id": "spacer", "title": "Square spacer", "blurb": "30 × 30 × 12 mm · central ⌀10 bore",
     "program": ('element = box("spacer", 30, 30, 12)\n'
                 'hole(element, 10.0, (0, 0))\n')},
    {"id": "flat_bar", "title": "Flat bar", "blurb": "200 × 25 × 8 mm · four M6 holes",
     "program": ('element = box("flat_bar", 200, 25, 8)\n'
                 'clearance_hole(element, "M6", (-75, 0))\n'
                 'clearance_hole(element, "M6", (-25, 0))\n'
                 'clearance_hole(element, "M6", (25, 0))\n'
                 'clearance_hole(element, "M6", (75, 0))\n')},
    {"id": "gusset", "title": "Gusset plate", "blurb": "100 × 100 × 5 mm · two M10 holes",
     "program": ('element = box("gusset", 100, 100, 5)\n'
                 'clearance_hole(element, "M10", (-30, 0))\n'
                 'clearance_hole(element, "M10", (30, 0))\n')},
    {"id": "precast_panel", "title": "Precast panel (BIM)",
     "blurb": "3000 × 2000 × 200 mm · two M16 cast-in anchors",
     "program": ('element = panel("precast_panel", 3000, 2000, 200)\n'
                 'anchor(element, 17.5, (-750, 0), 150)\n'
                 'anchor(element, 17.5, (750, 0), 150)\n')},
    {"id": "stacked_plates", "title": "Stacked assembly",
     "blurb": "60 × 60 × 10 base + 40 × 40 × 10 top",
     "program": ('base = box("base", 60, 60, 10)\n'
                 'top = box("top", 40, 40, 10)\n'
                 'stack(base, top)\n'
                 'element = assembly("stacked_plates", base, top)\n')},
    {"id": "stair", "title": "Stair flight (AEC)",
     "blurb": "17 risers · 170 rise / 280 going · 1000 wide",
     "program": 'element = stair("stair", rise=170, going=280, width=1000, riser_count=17)\n'},
]

_BY_ID = {s["id"]: s for s in SEEDS}


def by_id(seed_id: str) -> dict | None:
    """The full seed (incl. trusted program) for a given id, or None."""
    return _BY_ID.get(seed_id)


def program_for(seed_id: str) -> str | None:
    """The trusted program text for a seed id, or None if unknown."""
    s = _BY_ID.get(seed_id)
    return s["program"] if s else None


def listing() -> list[dict]:
    """Public listing — id/title/blurb only, never the program (the client picks by id)."""
    return [{"id": s["id"], "title": s["title"], "blurb": s["blurb"]} for s in SEEDS]


def programs() -> list[str]:
    """All trusted seed programs — the allow-set the safety validator checks derivatives against."""
    return [s["program"] for s in SEEDS]
