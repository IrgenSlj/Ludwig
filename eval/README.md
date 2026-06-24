# Ludwig eval harness

A fixed brief suite scored by the (validated) vision critic, so quality is
**measured**, not asserted. Each brief runs as one isolated candidate — no
panel, no rounds, no hero — so the only variable is the build path. That lets us
A/B one-shot vs `--agentic` and track quality across changes over time.

```bash
# baseline (stateless one-shot worker)
python3 ludwig.py --eval

# the other arm (self-correcting agentic worker) — prints the A/B delta
python3 ludwig.py --eval --agentic

# compare models / providers too
python3 ludwig.py --eval --model opus
python3 ludwig.py --eval --provider opencode
```

Every run appends one JSON line to [`results.jsonl`](results.jsonl): timestamp,
mode, model, provider, mean score, per-axis means, and per-brief scores. The run
prints its mean and, if a prior run of the *other* mode exists, the A/B delta.

Why it's trustworthy: the critic was measured to be stable (within-image stdev
≈ 0.2) and to rank strong vs. weak renders cleanly, so a single grade per render
is a usable signal. The suite is intentionally frozen — changing `EVAL_BRIEFS`
breaks comparability with past history.

## Findings so far (5-brief suite, 1 run each — directional, not airtight)

| mode | mean | notes |
|------|------|-------|
| one-shot | 5.0 | baseline |
| agentic ×1 turn | 5.0 | **+0.0** — one self-correction turn doesn't earn its cost |
| agentic ×3 turns | **5.52** | **+0.52** — real, modest lift; materials/brief/believability each +0.8 |

Takeaways: (1) self-correction needs **enough turns** (≥3) to matter; one is a
no-op. (2) The lift is modest at ~2.7× wall-cost, so agentic suits the final
hero render, not fast iteration. (3) ~2 of 5 briefs' first refinement *errored*
(the refined script broke in Blender) — so refinement **reliability** is the
lever to make agentic pay off more. (4) Even at its best the suite caps ~5.5/10,
which points back at the geometry **substrate** as the real ceiling.

Caveat: n=5, single run; per-brief generation is noisy (~±0.6), so treat these
as directional. Re-run for a second sample before betting on the deltas.

## Substrate experiment: retrieve-and-arrange (`--assets`)

Tests the thesis that the geometry **substrate** is the real ceiling. In
`--assets` mode the model calls `L_asset(query)` to import a real CC0 Poly Haven
mesh for the subject instead of sculpting it from primitives, falling back to
primitives when no asset matches (`L_asset` returns `None` below a match
threshold). Run on the same frozen suite, so it's a fair, conservative A/B vs
the primitive baseline: real meshes where they exist (mug/stool/lamp), primitive
fallback where they don't (perfume bottle/boots have no CC0 match). The
mechanism is proven — e.g. "ceramic vase" imports a real 9.4k-poly hand-glazed
vase, a different league from a sculpted grey ovoid.

### Result (surprising, and decision-grade)

| mode | mean | BRIEF axis |
|------|------|-----------|
| one-shot (primitives) | 5.0 | 5.0 |
| agentic ×3 (primitives + self-correct) | **5.52** | **5.8** |
| **assets (retrieval)** | **4.8** | **4.2** |

Retrieve-and-arrange did **not** win — it slightly *lost* (-0.2 vs one-shot), and
its **BRIEF-adherence axis was the worst of any mode (4.2)**. Per-brief: the real
bar chair edged the primitive (+0.4), the mug tied, but the desk lamp *regressed
-1.6* — the retrieved lamp was a gorgeous orange clamp anglepoise when the brief
asked for a *minimalist metal* one. The geometry was better; it was the wrong
object, and you cannot re-prompt a downloaded mesh into the brief.

Conclusion: on steerable product briefs the binding constraint is **brief-
adherence / composition, not geometry crudeness**. Self-correction raises it
(5.8); retrieval lowers it (4.2). So **sculpt-and-self-correct for the steerable
hero subject; reserve retrieval for non-steered props/context** — which is also
exactly what preserves Ludwig's design-as-code editability moat.
