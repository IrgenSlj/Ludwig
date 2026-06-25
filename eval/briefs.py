"""The FROZEN, held-out brief set ([H6]). Quality is measured against this, never tuned on it.

Each brief declares the named dims (mm) and hole count the critic enforces. Grow the set; do not
fit codegen/prompts to it. Pure data — no kernel import — so it loads anywhere.
"""

BRIEFS = [
    {"id": "bracket", "prompt": "a steel bracket, 80 × 40 × 6 mm, two M8 clearance holes",
     "dims": {"length": 80.0, "width": 40.0, "height": 6.0}, "holes": 2},
    {"id": "plate", "prompt": "a flat steel plate, 120 × 60 × 10 mm, no holes",
     "dims": {"length": 120.0, "width": 60.0, "height": 10.0}, "holes": 0},
    {"id": "spacer", "prompt": "a square spacer, 30 × 30 × 12 mm, with a central ⌀10 bore",
     "dims": {"length": 30.0, "width": 30.0, "height": 12.0}, "holes": 1},
    {"id": "flat_bar", "prompt": "a flat bar, 200 × 25 × 8 mm, four M6 clearance holes in a row",
     "dims": {"length": 200.0, "width": 25.0, "height": 8.0}, "holes": 4},
    {"id": "gusset", "prompt": "a gusset plate, 100 × 100 × 5 mm, two M10 clearance holes",
     "dims": {"length": 100.0, "width": 100.0, "height": 5.0}, "holes": 2},
]
