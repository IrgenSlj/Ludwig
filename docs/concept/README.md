# Ludwig — Architecture-vertical concept board

**`architecture-vertical.html`** — a single, self-contained, offline concept / vision
artifact for the architecture vertical. Open it in any browser (no server, no CDN, no build).
It is a pitch + thinking asset, not a production UI; it makes one bet legible in a glance:

> **Language in → an editable building model *and* coordinated drawings (plan + section,
> true vector geometry) → re-prompt one dimension and the *drawing* updates with the model.**

It extends — does not replace — the "Stage & the Director" paradigm and "graceful
crystallization" from [`../UX_BRIEF.md`](../UX_BRIEF.md). The Director still directs; the
Stage now holds a *building* and its *drawings*.

## What's in it (the three asked-for deliverables)

1. **The key visual** — one design shown as three synced views: the conversation (Intent),
   the editable model (Stage, an oblique B-rep line model), and the coordinated drawing
   (Sheet — a dimensioned stair section + plan with a title block). The lede states the
   thesis: the 3D, plan and section are *projections* of one typed model, never separate files.
2. **The hero moment** — the `⟳ re-prompt: "make the stair 320 mm going"` button (and the
   live `going` slider). It animates the dimension 280 → 320 and **every view re-derives
   together**: the section's going dimension, the run total (`17 G @ 320 = 5440`), the plan,
   the title block, and the 3D. The drawing updating is the point — a toast and the
   teal "RE-DERIVED" flags mark it. *This is the success test: "wait — the drawings update
   when you re-prompt?"*
3. **Crystallization, applied to a building** — the bottom band morphs a stair section from
   a loose graphite sketch (jittered, undimensioned) to a locked, line-weight-correct,
   dimensioned drawing. Precision *emerging*, not magic-blob generation. Scrub it.

## Why it's plausible, not vapor (the credibility signals)

- The geometry is **real parametric draughtsmanship**, recomputed from one parameter set —
  the section's "320" is re-derived from the number, not swapped art.
- Line weights are the **literal values** from [`../../standards.yaml`](../../standards.yaml)
  `drawing.line_weights_mm` (cut .50 / visible .35 / hidden .18 / centre .13 / dim .13).
- The stair survives an architect's gut check: 18 risers @ 166.7 mm, 2R+G ≈ 613 mm, pitch
  ≈ 31° — inside Approved Document K — and it *stays* compliant across the whole slider
  (the "standards-aware, not a pretty blob" message).
- Art direction is the project's own: warm paper / deep graphite, humanist sans + drafting
  mono, hairline rules, one restrained accent — the same tokens as `backends/present.py`.

## Reconciliation flag (raised, not silently resolved)

Both founding handoffs frame Ludwig as *at the spike stage* — the design brief says
designing real screens now would be "designing for a product that does not yet exist."
**In this repo that premise is already obsolete:** the B-rep loop converges and is measured
(60% first-pass / 100% post-repair — `docs/FINDINGS.md`), the conventioned shop-drawing
engine ships (`backends/shopdrawing.py`), and the webapp (`cli.py --serve`) already
re-derives drawings on re-prompt. So this concept's central question is not aspirational —
**it's demonstrable today.** That's a stronger pitch position; the board is written to lean
into it (the "honest about state" footnote, the masthead "the running engine already does
this"). When production UI work begins (Phase 3 proper), wire these frames to the real
`/api/compile_stream` + `shopdrawing` output rather than the hand-authored SVG here.

## Grabbing frames for a deck

The artifact is interactive, but each state screenshots cleanly:
- **Frame A** (the synced board) — load it; the Sheet reads `280` / `4760`.
- **Frame B** (the hero) — click `⟳ re-prompt`; the Sheet reads `320` / `5440`, the Intent
  log shows the edit, the "RE-DERIVED" flags light. Screenshot mid- or post-animation.
- **Frame C** (crystallization) — drag the scrubber to ~5% (loose sketch) and ~100%
  (locked, dimensioned) for the before/after pair.

No tooling required to view: `open docs/concept/architecture-vertical.html`.
