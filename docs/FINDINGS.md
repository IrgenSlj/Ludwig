# Ludwig — research findings

A log of what we've *measured*, not assumed. Every claim here is backed by a run
recorded in [`eval/results.jsonl`](../eval/results.jsonl) or a reproducible
experiment. Numbers are from a frozen 5-brief product-render suite graded by the
vision critic; unless noted they are single-run (n=5), so treat deltas under ~1.0
as directional. Re-run with `--eval --eval-repeats 3` to tighten them.

## P0/S3 — First-pass geometric pass-rate: the [H1] baseline

**60% (3/5)** on the frozen brief set — the first time the loop generated real CadQuery against the
thin element-API (`cli.py --eval --live`, `claude` default model, **first-pass, no repair**).

- Lands almost exactly where the sourced due-diligence predicted (Query2CAD 53.6% geometric-correct;
  CAD-Coder IoU ~0.52). The ~50%-first-pass reality behind **[H1]** is now **measured, not asserted** —
  which is precisely why we did *not* mandate "element-API only": every point of reliability matters here.
- Passed: bracket, spacer, flat_bar. Failed (first-pass): plate, gusset. *Why* is not yet diagnosed —
  the S4 deterministic critic returns structured per-check failures (wrong extent / axis orientation /
  unrequested feature), which will name the cause. The repair loop (`rounds>0`) is the mechanism meant
  to close this gap; a **post-repair** rate is the next measurement.
- This is the number to watch every phase. Prompt/toolkit/standards changes are judged against it on the
  held-out set, never fitted to it.

> Method: single run (n=1/brief), `claude` default tier — directional until repeated. Re-measure with
> `cli.py --eval --live`.

## P0/S4 — Post-repair pass-rate: the deterministic loop closes the gap

**100% (5/5) post-repair** vs **60% first-pass** on the same frozen set (`cli.py --eval --live --repair`,
≤2 repair rounds, claude default).

- This is the thesis, measured: a *deterministic* critic (exact dim/manifold/hole checks) hands repair an
  unambiguous error signal, and the loop converges where one-shot codegen doesn't. plate and gusset — the two
  first-pass failures — were both repaired to passing.
- It's why precision CAD is a *better* regime for the agentic loop than rendering was: the mesh-era vision
  critic was noise-limited (stdev ~0.2 on a 0–10 scale, below the deltas we chased — see §1 history); the
  geometric critic's signal is exact, so repair is reliable rather than a gamble.
- Watch both numbers each phase: **first-pass** (raw codegen reliability, [H1]) and **post-repair** (what the
  loop ships). The gap between them is the value the loop adds.

> Method: n=1/brief, ≤2 rounds, claude default — directional. Re-measure with `cli.py --eval --live --repair`.

---

## Mesh-era findings (historical — vision critic / Blender substrate, pre-re-foundation)

## 1. The critic (the moat's instrument) is reliable

Before trusting the self-correcting loop, we measured the grader itself: the same
render graded 4× swings by **stdev ≈ 0.2** (not the ±1.5 we feared), and it cleanly
**rank-orders** a strong render over a weak one (worst-strong 5.8 > best-weak 4.4).

> So "a reliable judge tells us what to build next" rests on real ground. Open
> question: fine discrimination between two *similar mediocre* candidates (the
> probe used far-apart renders).

## 2. The binding constraint is brief-adherence / composition — NOT geometry

This is the session's headline. The BRIEF-adherence axis across modes:

| mode | overall mean | BRIEF axis |
|------|--------------|-----------|
| one-shot (sculpt primitives) | 5.0 | 5.0 |
| **agentic ×3** (sculpt + self-correct) | **5.52** | **5.8** |
| assets (retrieve real meshes) | 4.8 | **4.2** ← worst |

Better geometry did not produce better renders. What moves the score is whether
the image *matches the brief* and is *well composed* — and self-correction raises
that, while retrieval lowers it.

## 3. Retrieve-and-arrange loses on steerable subjects (and that's the moat)

We built `L_asset(query)` → fetch a real CC0 Poly Haven mesh (no API key, 481
product/furniture models), import it headless. In isolation the geometry is
*gorgeous* — a real hand-glazed ceramic vase, a real anglepoise lamp, a different
league from a sculpted grey ovoid. But on the suite it **lost** (4.8 vs 5.0):

- The desk-lamp brief asked for "minimalist, metal arm"; retrieval returned a
  beautiful **orange clamp anglepoise**. Right-ish object, wrong styling, and you
  **can't re-prompt a downloaded mesh** into the brief → BRIEF axis tanks (−1.6).

> This empirically **vindicates the design-as-code moat**: a mesh blob is not
> steerable by language. Reserve retrieval for **non-steered props/context** (a
> plant, books, a bowl), where realism is free and brief-adherence doesn't apply;
> keep the **hero subject sculpted** so "make it taller / in brass" stays a
> re-prompt.

## 4. Agentic self-correction: modest, noisy, turn-hungry

`--agentic` makes each candidate view its own render and self-correct. Findings:

- **1 turn = no-op** (+0.0). It needs **≥3 turns** to matter (+0.52 at 3).
- Cost is ~2.7× wall time → suits the **final/hero render**, not fast iteration.
- It's the **only mode that raised BRIEF-adherence** (5.8), consistent with §2.
- Reliability matters: early runs had ~2/5 refinements **error in Blender**; we
  added a one-shot **repair** (feed the error back, keep the refinement intent)
  and a **void-guard** (reject refinements that render an empty frame). After the
  repair, all 5 briefs apply their full turn budget.

## 5. Methodology: single-run n=5 is noise-limited

Per-brief scores swing ~±1 between runs (perfume 5.8→0, lamp 6.8→5.2) — *larger*
than the mode deltas we chase. Conclusions under ~1.0 need averaging:
`--eval --eval-repeats 3`. A bug found this way: a failed refinement used to
render onto the shared output path (which `render()` pre-clears), destroying the
last-good render → spurious 0.0s. Fixed (render to a trial path, promote on
success). **Measuring caught it; asserting would not have.**

## Implications for the roadmap

1. **Quality lever is composition + brief-adherence, not substrate.** Invest in
   staging/composition intelligence and self-correction, not fancier geometry.
2. **Sculpt steerable heroes; retrieve only props/context.** Preserves the moat.
3. **Agentic is a "hero render" setting**, not the default — modest gain, real cost.
4. **Packaging** (separate analysis): not a Mac app (bundling Blender is heavy,
   mac-only). CLI now → thin *local* web UI (BYO Blender+model, zero hosting) →
   hosted webapp as the paid tier. Revenue wedge: one-sentence e-commerce shots.

## Acted on it (not yet eval-confirmed)

Following §2, the codegen brief now explicitly fights the measured failures:
**brief fidelity** (every named color/material/style word must be visibly true),
**no stray display props** (the recurring white pedestal under the subject), and
**fill the frame** (plus a tighter `L_autocam` margin 1.45 → 1.3). These are
principled and low-risk but **not yet proven** to lift scores — a single check
still showed the model rendering an asked-for "wooden table" as a white plinth,
i.e. brief-fidelity is hard and one rule doesn't force obedience. Confirm with
`--eval --eval-repeats 3` before claiming a gain.

## Reproduce

```bash
python3 ludwig.py --selftest                      # whole stack, ~2s, no API call
python3 ludwig.py --eval                           # one-shot baseline
python3 ludwig.py --eval --agentic --agent-turns 3 # self-correcting, prints A/B
python3 ludwig.py --eval --assets                  # retrieve-and-arrange
python3 ludwig.py --eval --eval-repeats 3          # noise-reduced measurement
```
