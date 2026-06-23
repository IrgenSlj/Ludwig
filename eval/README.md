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
