# Edit prompt (the re-prompt path — editability is the whole thesis)

You are given a working program and a change to make. Apply the change with the **smallest possible diff**.

## First: read the existing program structure

Before making ANY change, understand the program's:
- **Element IDs** — which `part()`, `box()`, `panel()` calls create which elements. Preserve these.
- **Named dims** — which `register_dim()` calls exist. You may ADD a dim for a new dimension you
  introduce, but never remove or rename an existing one unless the change explicitly requires it.
- **Spatial layout** — which coordinates holes are at, which offsets `place()` uses. Changing a hole
  coordinate is a one-line change; do not touch any other holes.
- **Standards usage** — `clearance_hole()` vs `hole()`. If the original uses `clearance_hole("M8",...)`,
  keep using `clearance_hole("M8",...)` unless the brief changes the spec.

## Hard rules
- **Change ONLY what the instruction requires.** Every other line must stay **byte-for-byte identical** —
  same names, same order, same spacing, same comments. A rewrite is a bug (BRIEF §10).
- **Preserve the element ID and structure.** Keep registering named dims for anything you change.
- **Consult `standards.yaml`** for domain semantics (e.g. an M10 clearance hole's diameter) — don't guess.
- If the change is impossible or contradictory, make the closest minimal change and nothing else.

## Dimension changes (the most common edit)

The user says "make the plate 100 mm wide instead of 80 mm."

1. Find the literal `80` that corresponds to plate width — e.g. `box("bracket", 100, 40, 6)` (change
   only the first argument of the `box` call).
2. Find the `register_dim("plate_width", ...)` call and update its value.
3. Change NOTHING else. Not the other dims, not the hole positions, not the comments.

Exception: if the width change means holes that were valid at x=30 are now outside the part, adjust
hole coordinates too — but ONLY those holes. Document with a comment that the adjustment is required
by the dimensional change.

## Structural changes (add/remove features)

The user says "add two more M6 holes at (±20, ±10)."

1. Read the existing hole pattern. Add the new `clearance_hole()` calls AFTER the existing ones.
2. The existing holes and their named dims must not change at all.
3. Keep all existing imports, the element assignment, and all other operations identical.
4. Only add the new lines — do not reorder, regroup, or "clean up."

Removing a hole: remove the single `clearance_hole()` or `hole()` line (or comment it out).
Do NOT re-index the remaining holes. Their named dims stay as they are.

## What counts as "byte-for-byte identical"

- Same import style (if the original uses `from toolkit import box, hole`, keep that exact import).
- Same variable names (if the original calls the element `element`, keep it `element`).
- Same whitespace (tabs vs spaces, blank lines between sections).
- Same comments (typo and all — changing a comment is a change).
- Same order of operations (holes in the order they were first written).
- Same `register_dim` names (never rename a dim unless the brief changes what it measures).

## Output
Return ONLY the full updated Python program — no prose, no markdown fences.
