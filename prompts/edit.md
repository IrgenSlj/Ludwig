# Edit prompt (the re-prompt path — editability is the whole thesis)

You are given a working program and a change to make. Apply the change with the **smallest possible diff**.

## Hard rules
- Change ONLY what the instruction requires. Every other line must stay **byte-for-byte identical** —
  same names, same order, same spacing, same comments. A rewrite is a bug (BRIEF §10).
- Preserve the element id and structure. Keep registering named dims for anything you change.
- Consult `standards.yaml` for domain semantics (e.g. an M10 clearance hole's diameter) — don't guess.
- If the change is impossible or contradictory, make the closest minimal change and nothing else.

## Output
Return ONLY the full updated Python program — no prose, no markdown fences.
