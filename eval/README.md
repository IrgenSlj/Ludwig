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
