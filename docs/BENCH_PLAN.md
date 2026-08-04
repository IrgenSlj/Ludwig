# B-series — measure on someone else's set, verify someone else's geometry

*The plan of record for the benchmark + foreign-geometry workstream, decided 2026-08-04 after a
competitive-technology review of Autodesk / PTC-Onshape / Zoo / the DFM tool category. Sits alongside
the A-series ([HARNESS_BRIEF.md](../HARNESS_BRIEF.md)) and D-series ([MACOS_APP_PLAN.md](MACOS_APP_PLAN.md));
tracked in [STATUS.md](STATUS.md). Specs it does not change: BRIEF.md's locked decisions stand.*

## Why this, why now

Two findings from the 2026-08-04 competitive review drive the whole series:

**1. The MCP surface is now commodity.** Autodesk shipped Fusion MCP with Anthropic (April 2026), plus
Fusion Data MCP and a Revit Public MCP, and is building a marketplace so certified third-party MCPs are
callable inside Autodesk Assistant. PTC shipped an Onshape MCP toolkit (Onshape Labs, July 2026). "An MCP
that does CAD" no longer differentiates — Autodesk gives it away to drive seats. **What none of them ship
is a deterministic verifier that gates the output.** The scarce good in an agentic CAD world is the thing
that says *no*, and it gets more valuable as everyone's generation gets faster. That is `critic/`.

**2. Our tracked number is measured on a set we wrote ourselves.** `eval/briefs.py` is 15 briefs, all
prismatic — boxes with holes, fillets, slots, one L-section, one stair. 93% first-pass / 100% post-repair
is *true* and it is *L1*. Meanwhile **BenchCAD** (arXiv 2605.10865) is public on HuggingFace, is
**CadQuery-native** — our exact substrate — and is built from 17,900 execution-verified programs across
106 industrial part families drawn from 47 ISO/DIN/EN/ASME/IEC standards, exercising 49 operations
(lofts, sweeps, helices, involute gears). Frontier MLLMs cap around 0.40 on its Vision2Code task;
on Text2CAD-Bench frontier models hit 68–70% *invalidity* on L3 (sweep/loft/shell).

So there is a third-party, substrate-matched, standards-derived benchmark where our exact claim —
*a deterministic critic plus repair closes the gap linear codegen leaves open* — is testable in public.

**We will score badly at first.** `toolkit/elements.py` has ~18 ops; BenchCAD exercises 49. That is the
point: per [FINDINGS.md](FINDINGS.md), the 60→93 jump came from *failures naming the missing capability*,
not from prompt tuning. A bad first number on a real set is worth more than a good number on our own.

## What is actually in the dataset (verified 2026-08-04, HF datasets-server)

`BenchCAD/BenchCAD` has three configs:

| config | rows | fields | fit |
|---|---|---|---|
| `code_gen` | 17,900 | `stem`, `family`, `variant`, `difficulty`, `base_plane`, `standard`, `code`, 5 renders | **Poor.** No text prompt — it is a Vision2Code set. Using it for text→CAD means synthesizing our own prompts, which forfeits the third-party claim. |
| `QA` | 2,400 | `stem`, `family`, `gt_code`, `composite_png`, `standard`, `qa`, `qa_level` | Later. Needs a query surface over the IR (see B5). |
| **`edit-bench`** | **748** | **`instruction`**, **`orig_code`**, **`gt_code`**, `orig_step`, `gt_step`, `iou`, `family`, `edit_type`, `category`, `category_label` | **Exact fit.** Natural-language instruction + a real CadQuery program → the edited program, graded geometrically. No VLM. |

`edit-bench` is the entry point, and it is the *better* one: instruction-guided minimal-diff editing is
Ludwig's locked thesis (BRIEF §10: "`--edit` must produce a minimal diff; a rewrite-on-edit is a bug"),
and it is the task nobody else benchmarks well. The published comparison point is **GPT-5.3 (thinking) at
0.865 normalized accuracy**.

**What the 748 rows actually ask** (measured 2026-08-04, so B3's headline number can be read honestly):

| category | label | rows | share |
|---|---|---|---|
| T1 | `literal_replace` | 180 | 24% |
| T2 | `chain_transform` | 104 | 14% |
| T3 | `relative_compute` | 111 | 15% |
| T4 | `feature_edit` | 199 | 27% |
| T5 | `geometry_rebuild` | 154 | 21% |

Nearly half (48%) is T4/T5 — feature edits and geometry rebuilds, not parameter tweaks. **72% of
instructions contain a number; only 26% state an explicit target value** ("…from 4.5 to 5.85"). That
last figure is a caution for B4: a critic that verified an edit against a target parsed from the
instruction would cover barely a quarter of the set, so it is not the general answer it first looks like.
Sampling is stratified by *family*, not category — check the category mix of any partial run before
reading its number as representative.

Bonus: `orig_step` / `gt_step` are real ISO-10303-21 STEP files — 1,496 industrial parts from 106
families, free fixtures for B2.

## Sequence

One session = one commit to `main`, `--selftest` green at every step, push often.

### B1 — the edit-bench harness, and a grader we have validated *before* spending a token
- `eval/benchcad.py` — dataset loader. Downloads the parquet over stdlib `urllib` into a gitignored
  `data/`, reads it with a **lazily imported** `pyarrow` (core stays dependency-light; `--selftest`
  stays green without it). Deterministic stratified sampling by `family` so a partial run is honest.
- `geometry/service.py` — `import_step`, `volume`, and `iou(a, b)` computed with **exact OCCT booleans**
  (`Vol(A∩B) / Vol(A∪B)`), not voxels. Sharper than BenchCAD's 256³ voxel IoU, and deterministic; the
  metric difference gets stated in FINDINGS rather than papered over.
- `eval/editbench.py` — foreign-program execution + the grader. BenchCAD programs assign `result` and
  call `show_object(...)`; `agent.loop.execute` requires `element`. A foreign adapter bridges this
  **without** loosening the trusted-program rule.
  Normalized accuracy = `(IoU(pred,gt) − IoU(orig,gt)) / (1 − IoU(orig,gt))`, clamped to [0,1].
- `cli.py --eval --bench edit [--bench-limit N] [--oracle]`.
- **Gate — the load-bearing step: validate the grader in oracle mode.** Feeding `gt_code` as the
  prediction must score **1.0**; feeding `orig_code` unchanged must score **0.0**. Both token-free.
  A grader that cannot pass its own oracle cannot be trusted to grade a model.

### B2 — verify geometry Ludwig did not author
`critic/geometric.py`, the `min_wall` check in `critic/manufacturing.py`, and `critic/printability.py`
all run off `el.geometry` alone with no dependence on the manifest (verified by reading them). So:
STEP in → wrap as an Element → run the panel → deterministic fabricability verdict.
- `cli.py --verify-file <path>` + a `ludwig_verify_file` MCP tool.
- The dimensional critic must report **N/A honestly** for an imported solid with no registered dims,
  never vacuum-pass.
- Fixtures: `orig_step` from B1's dataset.
- *Why it matters:* this is the Protolabs/Xometry DFM value unbundled, local and agent-callable, and it
  makes Ludwig **complementary** to Fusion MCP / Onshape / Zoo instead of competing for the generation
  slot. Much larger market than text-to-CAD.

### B3 — the live run + FINDINGS
`--eval --bench edit --live` on a stratified sample. Record normalized accuracy, execution rate, and the
**minimal-diff metric** (our diff size vs the ground-truth diff size — the claim nobody else measures)
against the published 0.865. FINDINGS entry either way, with the metric caveat stated.

### B4 — capability to-do list from the failures
Whatever the B3 failures name, in the order they name it. Expect missing ops (loft/sweep/shell/helix).
Per [H1] the fix is *adding the capability*, not tuning the prompt.

### B5 — `ludwig_query`: the IR as a queryable surface *(stretch, from the Autodesk AEC Data Model idea)*
Their bet is exposing geometry + properties + relationships as structured queryable data rather than
files. Ludwig's `backends/` is the Model Derivative equivalent, but there is no **read** surface — an
agent can only compile/verify/build/export. The IR already carries `params`/`manifest`/`features`/
`relations`; exposing them as a query turns Ludwig from a writer into a reader, which is where review
value lives. Also unlocks the `QA` config above as a second third-party number.

## Explicitly not doing
- **Bernini-style neural mesh generation.** Autodesk moved off it themselves — meshes are not editable.
- **A VLM judge / multi-view perception.** Rejected at M0; nothing here reopens it. `edit-bench` was
  chosen partly *because* it needs no vision.
- **PLM / data management.** That is the incumbents' moat, not a wedge.
- **Fitting anything to BenchCAD.** It is a held-out measurement set, exactly like `eval/briefs.py`.
  Capabilities may be added because a failure named them; prompts are never tuned against it.

## Sources
BenchCAD [paper](https://arxiv.org/abs/2605.10865) · [dataset](https://huggingface.co/datasets/BenchCAD/BenchCAD) ·
[Text2CAD-Bench](https://arxiv.org/abs/2605.18430) ·
[Autodesk APS agentic AI](https://aps.autodesk.com/blog/building-agentic-ai-whats-new-autodesk-platform-services) ·
[Fusion roadmap 2026](https://www.autodesk.com/products/fusion-360/blog/fusion-roadmap-2026/) ·
[Onshape Labs](https://www.ptc.com/en/news/2026/onshapelabs) ·
[Onshape branch & merge](https://www.onshape.com/en/features/branch-merge-cad) ·
[Zoo KCL](https://zoo.dev/research/introducing-kcl) · [DFMPro](https://dfmpro.com/)
