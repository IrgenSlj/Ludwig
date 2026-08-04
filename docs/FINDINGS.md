# Ludwig — research findings

A log of what we've *measured*, not assumed. The current precision-CAD findings are
at the top; the mesh-era vision-critic findings below them are kept as historical
record (clearly marked). The tracked number is the **first-pass geometric pass-rate**
over the frozen held-out brief set (`eval/briefs.py`) — reproduce any CAD finding with
`cli.py --eval [--live] [--repair]`. CAD numbers are single-run (n=1/brief) on the
`claude` default tier unless noted, so treat small deltas as directional.

## B1/B2 — the third-party benchmark, and verifying foreign geometry, 2026-08-04

**Why we went looking for someone else's set.** A competitive-technology review (Autodesk, PTC/Onshape,
Zoo, the DFM tool category — full write-up in [BENCH_PLAN.md](BENCH_PLAN.md)) turned up two facts. First,
the MCP surface is now commodity: Autodesk shipped Fusion MCP *with Anthropic* in April 2026 plus a Revit
public MCP, and PTC shipped an Onshape MCP toolkit in July. "An MCP that does CAD" no longer
differentiates. What none of them ship is a **deterministic verifier**, and the sharpest published critique
of Fusion MCP is that faster generation just floods a review process that was already the bottleneck.
Second, our own tracked number (93% / 100%) is measured on **15 briefs we wrote ourselves, all L1
prismatic**. So the number to go get is a third-party one.

**BenchCAD's `edit-bench` is the right entry point, and it was verified before committing to it.** Checked
against the HF datasets-server: the headline `code_gen` config (17,900 rows) carries **no text prompt** —
it is a Vision2Code set, so using it for text→CAD means synthesizing our own prompts and forfeiting the
third-party claim. But `edit-bench` (748 rows) carries `instruction` + `orig_code` + `gt_code` + real
STEP binaries: instruction-guided minimal-diff editing, which is Ludwig's locked thesis (BRIEF §10) and
needs no vision. Published comparison point: **GPT-5.3 (thinking) 0.865 normalized accuracy**.

**The grader was validated before a single token was spent — and it was wrong three times.** The gate is
`--eval --bench edit` in oracle mode: grading the ground truth must score 1.000 and grading the *unedited*
program must score 0.000. Every one of these was found that way, at n=100, and none would have been
visible from a passing run on our own briefs:

| # | what broke | the measurement |
|---|---|---|
| 1 | Compound handling | `ball_knob` is a sphere unioned with a **tangent** stem cylinder, so it is legitimately a 2-solid compound. `Compound.intersect(Compound)` returned one pair's common — the shape scored **IoU 0.247 against itself**. Fixed by fusing to pairwise-non-overlapping parts and intersecting part-wise. |
| 2 | No OCCT boolean is trustworthy alone | On `cotter_pin` the common returns **0** for a shape against itself while the fuse is correct; on `sheet_metal_tray` the common under-reports by **35%** and the fuse throws. Fuzzy tolerance (1e-7…1e-3) changes **nothing**. Intersections are now computed twice by different routes (`common`, and `va+vb−fuse`) and only trusted when they agree. |
| 3 | Congruence fooled by symmetry | `rib_plate`'s edit moves a symmetric rib array (`rarray(84.72)→rarray(46.4)`), preserving volume, bbox **and** centroid — so the short-circuit handed a free 1.0 for changing nothing. Congruence now also compares the **inertia tensor**. |

**Cross-validation of the metric.** After fix 3, `rib_plate` reads exact-boolean IoU **0.7935** against the
dataset's stored 256³ voxel IoU **0.7643**. The gap is voxel resolution error, and the agreement is close
enough to validate both — ours is the sharper of the two. State the metric difference wherever a number is
reported; BenchCAD's published figures are voxel-based.

**Ungradeable rows leave the denominator.** 4 of 100 rows cannot be graded by anyone: 1 where the
*dataset's own* program fails to build (`spline_hub`, OCCT `BRep_API: command not done`), 3 where the
kernel's booleans disagree with each other. Scoring those zero would blame the model for rows nothing
could pass. They are excluded and counted out loud. **Oracle gate, n=100 stratified over 100 families:
ground-truth 1.000 · unedited 0.000 · exec 100%, over 96 gradeable rows.**

**B2 — the critic runs on geometry Ludwig did not author.** `critic/geometric.py`, the `min_wall` half of
`critic/manufacturing.py`, and `critic/printability.py` all read the *solid*, not the manifest — so a STEP
from anywhere can be verified: `cli.py --verify-file <model.step>`, plus a `ludwig_verify_file` MCP tool.
Validated on real third-party STEP from BenchCAD: `battery_holder` legitimately **fails** min-wall at
0.500 mm; the bellows passes. The dimensional critic reports **n/a** rather than vacuum-passing, so
`passed` honestly means "no deterministic check failed", not "matches an intent" — there is no intent to
match — and the payload separates `checked` from `not_applicable`.

*Gotcha found here, same family as the STL one below:* with `--process`, the printability critic
tessellates the shape, and a bbox measured afterwards read **46.525 mm** for a 45.800 mm part. `_assemble`
is safe because the critic precedes the backends; on this path the tessellating critic is *inside* the
panel, so extents must be taken first. Fixed, and covered by the selftest.

**The minimal-diff instrument was measuring the wrong thing.** Over all 748 rows, **65% of the
ground-truth diff lines are comment-only** — the gt programs fill in a `# length = 92.8` parameter block
the originals leave blank. Counting those would have made any real edit look smaller than the reference
for free, flattering our own headline claim on bookkeeping Ludwig never did. `diff_size` now counts code
lines only. Caught *before* reporting a number, which is the only time it's worth anything.

**What edit-bench asks, so B3's number can be read honestly.** 748 rows: T1 `literal_replace` 180 (24%),
T2 `chain_transform` 104 (14%), T3 `relative_compute` 111 (15%), T4 `feature_edit` 199 (27%), T5
`geometry_rebuild` 154 (21%) — so **48% is feature edits and geometry rebuilds**, not parameter tweaks.
72% of instructions contain a number but only **26% state an explicit target value**. That last figure
rules out, in advance, the obvious "parse the target and verify the edit against it" critic as a general
answer. Sampling is stratified by *family*, not category; check a partial run's category mix before
calling its number representative.

**B3 (the live number) is NOT YET MEASURED — deliberately.** A 40-row live run was started and stopped at
~19 of ~25 minutes, because it predated two fixes landed in the same session (the `--bench-report` JSON
dump and the code-only `diff_size`). Reporting it would have meant publishing a number measured with an
instrument we had already found to be wrong. The harness is built, oracle-validated and smoke-tested
green at n=3 (3/3 exact, exec 100%); the exact command is in [BENCH_PLAN.md](BENCH_PLAN.md) §B3.

*Known limit to state when it does land:* edit-bench's dominant failure mode is **semantic** (right
shape, wrong number), and the deterministic critic can only see **structural** failure — won't execute,
or an invalid solid — when there is no declared intent to check against. So this benchmark is a strong
test of Ludwig's *editing*, and a weak test of its *repair thesis*. Naming that limit is part of the
result, not a caveat to bury.

## M0 — LUDWIG_V2_BRIEF audit, 2026-07-06

**The v2 brief models a different substrate than Ludwig has.** LUDWIG_V2_BRIEF.md ("the deliberative
harness") is written against a *belief* about the code — single-file `ludwig.py`, Blender/bpy generation,
single fixed-camera VLM critic, `results.jsonl` eval — and all seven of its §0.1 assumptions are false
against the repo (multi-package ~10.4k LOC; CadQuery/OCCT substrate; deterministic critic panel; geometric
pass-rate harness; `cli.py` verbs). The tell: **WS10 files CadQuery as a future "stub," but CadQuery/OCCT is
the whole shipped core** (STEP/IFC/DXF/STL + deterministic + printability critic), and **WS9 (MCP), filed as
Phase-2, already shipped** (A2–A4, external-agent pass-rate 93%). Full belief-vs-reality table, per-workstream
transfer analysis, and PyPI check (`ludwig` taken, `ludwig-harness` free) in **[AUDIT_NOTES.md](AUDIT_NOTES.md)**.

**Decision (Irgen, 2026-07-06): Option A — Retrofit onto CAD.** Keep the CadQuery/OCCT precision core +
deterministic critic; adopt only the substrate-agnostic machinery that measurably helps. **WS2 deliberative
branch-and-prune search is the first slice** — the deterministic critic is a *free, exact* pruner (cheaper
and sharper than the VLM pruning the source papers use), so the mechanism fits Ludwig better than the Blender
frontier it's borrowed from. Rejected: rebuilding on Blender (reverses the locked BRIEF.md:13 substrate call),
re-centering a VLM judge / multi-view perception (reverses locked principle #5), and BlenderGym/BlenderBench
(wrong benchmark family — BenchCAD/Query2CAD is the CAD-appropriate corpus). De-risking measurement for WS2:
critic-pruned search vs linear codegen on the frozen set, `--eval-repeats 3`, recorded here when run.

## A-series (agentic harness) — measured state, 2026-07-04

**MCP is the second face of the contract, and the transport preserves codegen reliability.** `cli.py mcp`
exposes compile/verify/plan/build/export (A2–A3); every result carries the critic verdict + `schema_version`;
export refuses on a failing critic; the Op-API is the only write surface (malformed ops rejected, nothing
exec'd). Verified by a real stdio MCP client: a valid plan round-trips with its inverse; a structural op
waits for `confirm`; export gates on the critic + the permission policy.

**External-agent pass-rate = 93% (14/15) — the gap to native is ZERO. The harness thesis, quantified.**
`cli.py --eval --mcp` drives each frozen brief through `ludwig_compile` over ONE stdio MCP session — Ludwig
as a stock external agent's tool — and grades with the *same* geometric gate as native. Clean full-set run
(2026-07-04, haiku codegen, first-pass, no repair): **93% (14/15)**, identical to the native live first-pass
rate (93%, 14/15, §below). So essentially **all** of Ludwig's codegen reliability survives being someone
else's tool over MCP — the §8 gap the A-series set out to measure is 0. The one miss is `stair_flight`,
reason `geom-miss` (built a valid solid, off the declared dims) — a genuine n=1 first-pass codegen miss, NOT
a harness artifact. (Native's lone miss that run was a *different* brief, `filtered_bracket`; `stair_flight`
passes natively — different briefs missing on different runs is exactly the ~7% one-shot LLM variance at
n=1, not a capability gap. `filtered_bracket` *passed* via MCP here, corroborating the "variance, not gap"
read.)

**How the 47% throttling artifact was killed at the root (not waited out).** The earlier run reported 47%
(7/15) purely because 15 sequential live compiles burst the inference CLI's rate/session limit partway
through — every late failure was an empty program, and each "failed" brief passes in isolation via the same
tool. Rather than re-run hoping for a quiet window, the harness is now *robust*: it **paces** itself between
briefs (`LUDWIG_EVAL_PACE_S`, default 6–8 s) and **retries only throttle-shaped** failures (empty program /
tool error / timeout — the CLI, not Ludwig) with real backoff (`LUDWIG_EVAL_RETRIES`, 20→40→80 s); a genuine
geometry/build miss is never retried, so the number stays honest. The inference seam (`agent/inference.py`)
also now backs off *longer* on rate-limit-shaped stderr so a single transient limit self-heals across the
whole product. The 93% run needed **zero** throttle-retries — pacing alone prevented the burst. Reproduce:
`.venv/bin/python cli.py --eval --mcp`. Watch it happen (token-free, no inference): `examples/mcp_walkthrough.py`.

**Repair corpus (A5) — infra built, UNMEASURED, default OFF (the entry principle #12 owes).** `store/repairs.py`
remembers (critic-failure → fix) pairs, keyed on a normalized failure signature, and injects the nearest past
fixes into the repair prompt as minimal diffs. It is **not yet measured**, so it ships **default off**
(`memory.repair_corpus`). *The measurement, still to run:* mine the corpus from the disjoint pool
(`cli.py --mine-repairs`, never the frozen set — no train-on-test), then `--eval --live --repair` with
`LUDWIG_REPAIR_CORPUS=on` vs `off`, comparing **average repair rounds** and post-repair rate. *Kill criterion:*
if the on/off delta on the frozen set is within n=1 noise (no reduction in repair rounds or tokens), it stays
default-off — the infra remains for the harder print3d/pack briefs where repair headroom is larger. Note the
thin frozen-set headroom (already 100% post-repair in ≤2 rounds) means the honest signal is in *rounds*, not
rate; measure accordingly.

**Printability critic (A7) — deterministic, validated, and a tessellation gotcha found & contained.** The
printability checks are exact geometry, not vibes: `print_mesh_stats` was validated to read a **90°** overhang
on a cantilever, **0°** on prismatic parts, and a bed-contact footprint matching the analytic area on a box
(3200 mm²) and cylinder (1252 ≈ π·20²). The min-wall/envelope gates fire on a thin-wall/oversize FDM part with
the right message; overhang/bed-contact advise without blocking (support/brim are normal print practice, not
defects). **Gotcha (measured):** exporting an STL adds an OCCT triangulation to the shape, and a triangulated
shape's `BoundingBox()` bloats by the deflection (a 6.000 mm box read **6.025** mm after STL). Harmless in the
pipeline — the critic runs *before* backends in `_assemble`, so the exact-dim verdict and payload bbox are
computed first (confirmed: adopt reports 80×40×6 exactly with STL registered) — but never tessellate a shape
you will re-measure exactly. The selftest anchors a fresh throwaway part for the STL check for this reason.

## Interaction-core (rebuild R1–R34) — measured state, 2026-07-01

The no-LLM interaction core (recorded FeatureGraph → deterministic evaluator + targeted literal
substitution) now carries the whole direct-manipulation surface **token-free** (`$0` inference/visitor):
extent sliders + **face-drag** (R10: grab a 3D face → its extent dim updates live, commit is a +1/−1
diff), **live 2D sketch edit** (R34: drag a sketch distance dim → re-solve + re-extrude, 2D & 3D in
lockstep), **live cut plane** (R33), the **section drawing backend** (R30 poché sheet), and the
**sketch DoF critic** (R32). Gate: `--selftest` kernel **57/57** / pure-Python **17/17** · `--eval`
**15/15 (100%)** · pytest **145** *(as of R34 completion; current count is higher)*. All browser-verified where interactive.

**Real generative pipeline validated end-to-end (2026-07-02).** With the whole rebuild shipped, a real
inference run (claude CLI, `cheap`=haiku codegen) on a fresh brief — "90×50×8 steel mounting plate,
four M6 clearance holes inset 12 mm at the corners" — produced valid toolkit code that built exactly
(90×50×8, holes at ±33/±13), passed **every** critic (watertight, dims, hole_count=4, min_wall),
**first-pass, 0 repair rounds**, and emitted STEP/IFC/SVG/shop-DXF/section-DXF. So the generative +
verify + derive loop works against a live model, not just the mocked tests — the local/BYO-key tier is
functional. Reproduce: `.venv/bin/python cli.py "<brief>"`.

**First-pass live pass-rate: 60% → 93% (14/15)** — lifted by *measurement-driven capability additions*,
not prompt-fiddling vibes. (`cli.py --eval --live`, haiku codegen, first-pass, no repair.) The arc:

| run | rate | what changed | who flipped to pass |
|---|---|---|---|
| baseline | **60%** (9/15) | — | — |
| +prompt | **67%** (10/15) | `_api_and_standards` now documents the FULL toolkit (it had never told the model `stair()`/`cylinder()`/`sketch()`/`wall()` exist) | `stair_flight` |
| +feature ops | **93%** (14/15) | promoted the oracle's proven cq methods to element-API ops: `fillet`/`chamfer`/`slot`/`counterbore`, documented | `slotted_plate`, `chamfered_spacer`, `counterbored_plate`, `l_profile` |

The one remaining fail — `filtered_bracket` (a 5 mm fillet on all top edges + two holes) — is NOT an op
or capability gap: the `fillet` op builds a valid solid whether the holes are drilled before OR after
it (measured directly — `faces('>Z').fillet(5)` on a pre-drilled plate is valid, so the fillet-order
"fragility" I first *assumed* here was wrong). It's single-brief first-pass variance from the model at
`n=1` — the honest ~7% an LLM misses on one run. **The load-bearing lesson:** the frozen eval's failures
are a precise capability to-do list; each fail named exactly the op the model couldn't reach for, and
adding the capability (not tuning the prompt) is what moved the number 60→93. Reproduce: `cli.py --eval
--live` (n=1/brief, so ±1 brief is noise).

**Post-repair live pass-rate: 100% (15/15)** — the *deliverable* metric, since the product runs the
generate→verify→**repair** loop. Measured `cli.py --eval --live --repair` (haiku codegen, opus repair):
every frozen brief builds a critic-passing solid, including `filtered_bracket` (the lone first-pass
miss). So first-pass 93% is the model's one-shot reach; 100% is what a user actually gets once the
repair loop closes the ~7% variance. The whole verified-fabricability thesis — generate, verify with a
deterministic critic, repair on failure — holds end-to-end against a live model.

**R11 (span-identity binding) is obviated by R8 — measured, not assumed.** R11 was scheduled to kill
the value-collision LLM fallback (a 30×30 square editing `length` moving `width` too). Measured: R8's
`_try_span_edit` already routes the spacer's `length` 30→45 through the deterministic fast path with
`agent.inference.infer` asserted **not called** — only `length` moves (45×30×12). Building R11's
`bind.py` + `L=80; box(id,L,…)` variable-binding infra now would be a premature abstraction with no
brief demanding it (CLAUDE.md: "Never pre-build the ontology"); revisit only when a real seed uses a
variable extent. Reproduce: patch `agent.inference.infer`, `edit_to_result(spacer, param=length 30→45,
allow_llm=False)` → `fast=True`, `infer.called is False`.

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

## P2 — Conventioned drawings: OCCT HLR is the wrong substrate; the IR's semantics are the right one

Probing OCCT HLR (`HLRBRep_Algo`) on the bracket before building the drawing engine produced two
disqualifying measurements:

- **Hidden edges came back empty.** `HCompound()` returned **0 edges** for the bracket's through-holes
  in the front/side projections — exactly the hidden-line convention a shop drawing needs most. The
  silhouette "hole wall" lines are view-dependent and aren't B-rep edges at all, so HLR can't emit them.
- **The view frame is ambiguous.** The projected coordinates land in the projector's local 2D plane, not
  the model frame; the pre-existing (never-run) `compile_dxf` read `(X, Z)` where the projected `Z` is
  always 0 — a degenerate, flat result. It had never been exercised by a test or the compile path.

Conclusion, consistent with BRIEF §7's warning that HLR is fragile: **derive the drawing from the IR's
semantics, not from kernel topology.** Ludwig *knows* a feature is "a ⌀9 hole THRU at (20, 0)", so it
authors the circle, the dashed hidden walls, the centre-line, and the callout directly — the conventioned
detail a kernel screenshot structurally cannot reconstruct. This is the same design-as-code thesis as the
rest of the compiler, applied to drawings; it is also why this surface is a moat (IFC "barely carries
annotation"). Straight silhouette edges still come from the solid (true outline for prismatic parts);
true HLR silhouettes for non-prismatic solids are a later refinement. Reproduce: `cli.py --selftest`
(the shop-drawing gate) or compile any brief and open `out/<id>.dxf` / `out/<id>.png`.

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

## Reproduce (current precision-CAD CLI)

```bash
python3 cli.py --selftest              # the regression gate — whole spine, no LLM tokens
python3 cli.py --eval                   # pass-rate on the deterministic reference oracle (100%)
python3 cli.py --eval --live            # first-pass geometric pass-rate on real LLM codegen ([H1])
python3 cli.py --eval --live --repair   # post-repair pass-rate — the full loop + critic panel
```

The mesh-era commands (`ludwig.py --agentic/--assets/--eval-repeats`) were retired in the
re-foundation; they remain runnable only at the git tag `mesh-era-m4`.
