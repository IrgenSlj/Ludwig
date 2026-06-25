# Repair prompt (the compiler's error-driven fixup)

You are given a program, the IR it built, and the critic's failures as JSON. Fix **only** the
failures. Preserve intent and everything that already passes.

## Hard rules
- **Minimal change.** Touch only the lines responsible for the failed checks. A rewrite is a bug —
  editability is the whole thesis, and a minimal diff is how the user trusts the change.
- **Do not chase the critic into new failures.** If a fix risks a passing check (e.g. a fillet radius
  vs min-wall), say so and choose the conservative option.
- OCCT throws opaque `StdFail_NotDone` on bad fillet/boolean (BRIEF §8). If you see it: reduce the
  offending radius, add `.clean()` after booleans, or reorder ops — don't blindly retry.

## Output
Return ONLY the full corrected Python program — no prose, no fences.
