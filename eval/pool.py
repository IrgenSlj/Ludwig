"""The repair-corpus MINING pool (A5) — briefs to learn repair patterns FROM.

Deliberately DISJOINT from the frozen held-out set (`eval/briefs.py`): the repair corpus is mined
from these, then its effect is measured on the frozen set. Mining from the frozen briefs would be
training-on-test (HARNESS_BRIEF §12 / the "measured against, never tuned on" rule). Grow this pool
freely — it is the corpus's teacher, never the exam.

Chosen to exercise the repair paths the R-series found real: a wall thinner than min_wall, holes that
crowd an edge, a feature (fillet/chamfer/counterbore/slot) the first pass often mis-reaches for, a
non-box profile via sketch, and an assembly. Each is fabricable once repaired.
"""

POOL = [
    {"id": "p_thin_bracket",
     "prompt": "a steel bracket, 60 × 30 × 5 mm, two M6 clearance holes 8 mm from each end",
     "dims": {"length": 60.0, "width": 30.0, "height": 5.0}, "holes": 2},
    {"id": "p_wide_plate",
     "prompt": "a flat steel plate, 150 × 90 × 8 mm, four M8 clearance holes at the corners inset 15 mm",
     "dims": {"length": 150.0, "width": 90.0, "height": 8.0}, "holes": 4},
    {"id": "p_deep_spacer",
     "prompt": "a square spacer, 25 × 25 × 20 mm, with a central ⌀8 bore",
     "dims": {"length": 25.0, "width": 25.0, "height": 20.0}, "holes": 1},
    {"id": "p_long_bar",
     "prompt": "a flat bar, 240 × 30 × 6 mm, five M5 clearance holes evenly spaced in a row",
     "dims": {"length": 240.0, "width": 30.0, "height": 6.0}, "holes": 5},
    {"id": "p_filleted_plate",
     "prompt": "a steel plate, 90 × 50 × 8 mm, with a 4 mm fillet on all top edges and two M6 holes",
     "dims": {"length": 90.0, "width": 50.0, "height": 8.0}, "holes": 6},
    {"id": "p_chamfered_bore",
     "prompt": "a round spacer, ⌀40 × 15 mm, ⌀16 central bore with a 1.5 mm chamfer on both bore edges",
     "dims": {"length": 40.0, "width": 40.0, "height": 15.0}, "holes": 1},
    {"id": "p_slotted_bar",
     "prompt": "a flat bar, 120 × 40 × 8 mm, with a central slot 8 mm wide × 30 mm long",
     "dims": {"length": 120.0, "width": 40.0, "height": 8.0}, "holes": 0},
    {"id": "p_counterbored",
     "prompt": "a steel plate, 100 × 40 × 12 mm, two M8 counterbored holes (⌀9 through, ⌀15 cbore 6 mm deep)",
     "dims": {"length": 100.0, "width": 40.0, "height": 12.0}, "holes": 4},
    {"id": "p_channel",
     "prompt": "a U-channel profile, 60 wide × 40 tall legs, 6 mm thick, extruded 120 mm long",
     "dims": {"length": 60.0, "width": 40.0, "height": 120.0}, "holes": 0},
    {"id": "p_offset_gusset",
     "prompt": "a gusset plate, 120 × 80 × 6 mm, two M10 clearance holes at (30, 20) and (-40, -25)",
     "dims": {"length": 120.0, "width": 80.0, "height": 6.0}, "holes": 2},
]
