# Ludwig eval harness

Quality is **measured, not asserted** (BRIEF §10 / [H6]). The single tracked number is:

> **first-pass geometric pass-rate** — over a *frozen, held-out* brief set, the fraction of briefs
> whose first generated program builds an IR that passes the deterministic critic (manifold +
> watertight + every brief-named dimension exact to `tolerances.linear`).

This is the number that predicts product viability. It replaces the mesh-era vision-critic scores,
which were noise-limited (per-brief swings exceeded the deltas we chased — see `../docs/FINDINGS.md`,
the finding that motivated the deterministic-first critic).

## Discipline
- **Held-out.** Never tune codegen/prompts on the eval set. Add briefs; don't fit to them.
- **First-pass is the headline.** Also report post-repair pass-rate and rounds-to-pass, but the
  first-pass number is the honest measure of codegen reliability ([H1], the central P0 bet).
- **Raw vs wrapped.** Track the pass-rate for raw-CadQuery codegen vs the thin element-API side-car —
  this is the experiment that decides how far the wrapper grows (BRIEF §8).
- **Anything that remains a ranking uses pairwise** judging, not absolute scores (lower variance).

## Status
Brief set + harness land in **P0/S2** (`cli.py`-driven, no hand-tuning). The mesh-era brief suite and
`results.jsonl` were retired in the re-foundation (recoverable at the git tag `mesh-era-m4`).
