# AUDIT_NOTES.md — M0 read-only audit of LUDWIG_V2_BRIEF.md against the actual codebase

*Milestone M0 (LUDWIG_V2_BRIEF §0.1, §7). Read-only. No code changed. Produced 2026-07-06.
The brief states its specs are written against the author's **belief** about the code and instructs:
"Where reality differs, write AUDIT_NOTES.md and adapt the spec — do not silently deviate." This is that file.
It found the brief's belief about the substrate is inverted from reality, which is a locked-decision-level
fork (§0.5) and is escalated to Irgen rather than silently adapted.*

---

## 0. TL;DR

**The v2 brief models a Blender-substrate, VLM-judged, scene/art-generation harness. Ludwig is a
CadQuery/OCCT precision-CAD/BIM compiler with a deterministic (non-vision) critic and shipped
fabrication + MCP surfaces.** The two collide on the load-bearing axis: **substrate and critic type.**

The clearest single tell: **WS10 treats CadQuery as a future "stub + one bracket path."** CadQuery/OCCT
is in fact the *entire current substrate*, shipping STEP/IFC/DXF/STL through a deterministic + printability
critic. The brief's reserved-future interface is Ludwig's shipped core. The inversion is exact:
brief = Blender core / CadQuery stub; reality = CadQuery core / Blender deleted.

Roughly half the brief's *machinery ideas* (deliberative branch-and-prune search, richer trajectory
context, telemetry/trajectory dataset, cross-model judging for the demoted aesthetic pass) are
substrate-agnostic and would genuinely strengthen Ludwig. The other half (multi-view VLM perception,
Blender physics/BVH symbolic layer, BlenderGym/BlenderBench benchmarks, the Blender-scorecard launch)
are predicated on the substrate Ludwig deliberately abandoned as "the wrong substrate for precision and
fabrication" (BRIEF.md:13).

**This needs an Irgen decision before any building (see §5).** Everything below is evidence for that
decision.

---

## 1. Belief-vs-reality table (the brief's §0.1 assumptions)

| # | Brief believes | Reality (verified this session) | Evidence |
|---|---|---|---|
| 1 | Single-file `ludwig.py` | No `ludwig.py`. Clean multi-package repo, ~10.4k LOC of Python across `ir/ geometry/ backends/ critic/ agent/ webapp/ toolkit/ store/ eval/ desktop/`. | `git ls-files '*.py'`; `wc -l` = 10,393 |
| 2 | Blender Python (bpy) generation; "CadQuery next" | **CadQuery/OCCT B-rep is the current substrate.** Blender appears only in Markdown and 3 *historical/negative* code comments ("as the mesh era exec'd bpy"; a panel comment; a skeleton test that deliberately avoids importing bpy). The Blender render backend was **deleted** this era (~535 lines, STATUS.md "Cleanup"). | `git grep -n bpy\|blender -- '*.py'` → only `agent/loop.py:297`, `critic/panel.py:12`, `tests/test_skeleton.py:1` |
| 3 | Linear agentic loop with summarized per-turn state | `generate → verify → repair` loop in `agent/loop.py`; codegen tier (cheap) writes CadQuery, repair tier (best) fixes only critic failures. | `agent/loop.py:1–16` |
| 4 | Single fixed camera critique (VLM image matching) | **Deterministic critic panel over the IR** (geometric, dimensional, semantic, manufacturing, compliance, sketch, printability). No camera, no render in the verify path. Vision is *locked as demoted* to aesthetic-only, render-backend-only (BRIEF §6, first principle #5). | `critic/panel.py:9–32`; BRIEF.md:65,165 |
| 5 | Same-model critic (self-judge, reward-hacking risk) | Critic is deterministic geometry, not a model — nothing to reward-hack. Inference is tiered (cheap codegen / best repair) via a provider-blind CLI seam. | `agent/loop.py:9–11`; `standards.yaml: inference.tiers` |
| 6 | `results.jsonl` eval output | Eval = **first-pass geometric pass-rate** over a frozen brief set (bbox vs declared dims within gate tol, hole count, valid solid). No `results.jsonl`. | `eval/harness.py:1–43` |
| 7 | CLI `ludwig generate / --edit / --agentic / --eval / --selftest` | CLI is `python3 cli.py` with `--selftest / --eval [--live --repair --mcp] / --edit / --plan / --apply / --serve / mcp / --mine-repairs`. No `generate` or `--agentic` verbs. | `cli.py:1036–1094` |

**Every one of the seven load-bearing beliefs is false.** The brief's §0.1 correctly anticipated this
possibility; §7's M0 gate ("AUDIT_NOTES reviewed by Irgen") is doing its job.

## 1a. Things the brief does not know are already shipped

- **WS9 (MCP server + Agent Skill), listed as Phase-2 future work, is largely shipped**: A2/A3/A4 delivered
  `cli.py mcp` (`agent/mcp.py`) exposing compile/verify/build/export, the Op-API permission gate
  (`agent/permissions.py`), and a runnable trust-arc walkthrough. Measured: **external-agent pass-rate
  93% (14/15), gap-to-native 0** (STATUS.md, FINDINGS). The brief's headline Phase-2 surface exists.
- **Fabrication backends ship today**: STEP/IFC/DXF + **STL with a printability critic** (A7), all critic-gated
  behind a pre-export hook. This is the "print3d wedge" the brief reserves for WS10's future.

## 1b. Locked decision D1 — PyPI name

Verified at execution time (curl to pypi.org/pypi/*/json):
- `ludwig` → **200 (taken)** — confirmed unavailable, as the brief predicted (the Uber/LF ML framework).
- `ludwig-harness` → **404 (available).** D1's chosen name is free. *(No opinion on whether to rename a
  working repo; noted only that the name is claimable.)*

---

## 2. The core architectural collision (BRIEF locked decisions the v2 thesis reverses)

The v2 brief's thesis — "*sees* its own output through renders … a cross-model VLM judge is the center …
prove it on BlenderGym/BlenderBench" — reverses three **locked** decisions in the founding BRIEF.md:

1. **Substrate.** BRIEF.md:13: *"The mesh kernel is the wrong substrate for precision and fabrication …
   we swap the substrate and the critic."* Ludwig moved off Blender **on purpose**. v2 moves back to Blender.
2. **Critic type.** BRIEF §6 / principle #5 (locked): *"Deterministic-first critic. The vision critic is
   demoted to soft aesthetic judgments on the render backend only … this is why precision CAD is a better
   regime for the agentic loop than rendering was — the error signal becomes exact."* v2 re-centers the
   VLM judge (WS3, WS4) and multi-view perception. The render backend it needs was just deleted.
3. **Truth & benchmark.** BRIEF: the typed IR is the truth; CadQuery is a service; fabrication files are
   backends; the tracked number is first-pass **geometric** pass-rate; the relevant literature is
   Query2CAD / CAD-Coder / CADSmith (CAD codegen, ~50% stock first-pass). v2's launch artifact is a
   **BlenderGym/BlenderBench photometric-loss / CLIP-similarity scorecard** — scene/art metrics that do
   not apply to a precision part. The brief itself concedes BenchCAD is the CAD-appropriate corpus but
   files it under WS10's future.

This is not spec drift adaptable by editing paths; it is a **product fork**. Hence escalation, per §0.5.

---

## 3. Per-workstream transfer analysis (what survives onto Ludwig's real substrate)

Rating = how much of the workstream transfers to Ludwig **as it actually is** (CadQuery core,
deterministic critic), keeping the good ideas and dropping the Blender assumptions.

| WS | Idea | Transfer | Notes |
|---|---|---|---|
| **WS0** Restructure to `src/ludwig_harness/` + rename | ◑ partial | Repo is already clean multi-package, not single-file — the "do the surgery once" premise is overstated. src-layout migration + rename of a 10.4k-LOC repo with a green 96-check selftest is high-churn, low-benefit now; golden-file parity premise references CLI verbs that don't exist. Recommend defer/scope-down. |
| **WS1** Trajectory engine (full multimodal interleaved context) | ◑ concept only | "Every render + critique interleaved" is Blender/VLM-world. But **full-trajectory context over code-diffs + deterministic critic reports** is a real, valuable upgrade to Ludwig's repair loop. Transfers in spirit, not letter (no renders to interleave). |
| **WS2** Deliberative branch-and-prune search (`veri_ratio`) | ● strong | Best fit in the brief. Ludwig already does `--candidates N`. Branch-and-prune where the **deterministic critic is the free, exact pruner** is *better* here than in the papers (VLM pruning is neither free nor exact). Genuinely additive. |
| **WS3** Multi-view VLM perception, concept-target | ○ low/negative | Ludwig's critic doesn't look at renders; the render backend was deleted. Re-introducing multi-view VLM judging contradicts locked principle #5. Applies only if we re-add a vision critic — a reversal, not an increment. |
| **WS4** Judge subsystem (cross-model, rubrics, honeypots) | ◑ partial | Deterministic critic can't self-prefer or reward-hack, so honeypots/rubric-versioning/cross-model-integrity mostly target a problem Ludwig designed away. The **pairwise cross-model idea does transfer to the one demoted aesthetic pass**. Structured-output + retry-repair discipline is good hygiene generally. |
| **WS5** Symbolic substrate (settle, BVH, relational DSL) | ◑ concept already true | The *insight* — "VLMs fail at precise spatial control → use a deterministic symbolic layer" — is **literally Ludwig's founding thesis, already shipped** (deterministic critic over exact B-rep). The Blender implementation (rigid-body settle, `mathutils.bvhtree`, scene composition) is N/A to precision parts. Nothing to build; concept validated. |
| **WS6** BlenderGym / BlenderBench integration | ○ N/A for CAD | Scene-editing benchmarks scored by photometric loss / CLIP-vs-goal-image. They do not measure a dimensionally-exact part. The CAD-appropriate benchmark is BenchCAD / Query2CAD / CAD-Coder (already cited in BRIEF for the ~50% number). **This is the crux of the fork:** the launch artifact only makes sense if the substrate is Blender. |
| **WS7** Telemetry & trajectory dataset | ● strong | Substrate-agnostic and additive. Ludwig has `out/ runs`, a repair corpus (A5), precedent-store scaffolding (A6). A pydantic run-manifest + trajectory schema + content-addressed media + `replay` determinism is a clean win. |
| **WS8** Skill-library learning (design-only) | ◑ concept | Mine trajectories for reusable ops → transfers to Ludwig's `toolkit/` element-API side-car. Note the brief's `L_*` naming is the **mesh-era Blender toolkit** (salvaged at tag `mesh-era-m4`), not Ludwig's current `toolkit/`. |
| **WS9** MCP server + Agent Skill | ✔ mostly shipped | See §1a. Re-scoping needed: this is A2–A4 done, not Phase-2 future. |
| **WS10** CadQuery substrate stub | ✔ inverted — it's the core | CadQuery isn't a stub; it's the whole shipped substrate (STEP/IFC/DXF/STL + deterministic + printability critic). The one thing the brief marks "prove the abstraction can plug in later" is the thing Ludwig has been for the whole R-series. |

Legend: ● strong transfer · ◑ partial / concept-only · ○ low/N-A · ✔ already exists.

**Summary:** WS2 + WS7 are strong, mostly-substrate-agnostic wins that would help Ludwig today. WS1/WS4/WS5/WS8
transfer as *concepts* (several already realized). WS3/WS6 and the Blender-scorecard launch are predicated on
the abandoned substrate. WS9/WS10 are miscalibrated against shipped reality.

---

## 4. Consequential deviations I must NOT silently make

Per §0.1 these are flagged, not executed:
- Do **not** rebuild on Blender / re-add bpy — reverses BRIEF.md:13 (locked).
- Do **not** re-center a VLM judge / multi-view perception — reverses BRIEF §6 principle #5 (locked).
- Do **not** rename the package or do the src-layout migration yet — high-churn, and premised on a
  single-file repo that doesn't exist; needs its own cost/benefit sign-off.
- Do **not** wire BlenderGym/BlenderBench — wrong benchmark family for a precision-CAD compiler.
- Do **not** treat CadQuery as a WS10 stub — it is the core; a "stub" PR would be a regression.

---

## 5. Reconciliation options (for Irgen — this is the M0 gate)

The audit can't choose between these; the choice is a business/direction call. Recommendation stated,
reasoning attached, so the decision is yours on evidence, not vibes.

- **Option A — Retrofit (recommended).** Keep Ludwig's CadQuery/OCCT precision-CAD core and deterministic
  critic. Adopt only the substrate-agnostic harness machinery that strengthens it: **WS2 deliberative
  search** (deterministic critic as free pruner) + **WS7 telemetry/trajectory dataset**, then **WS1**
  trajectory-context and **WS8** motif-mining as follow-ons. Launch artifact becomes a **CAD** scorecard
  (BenchCAD / Query2CAD-style first-pass on a public CAD set), not a Blender one. *Why:* preserves the whole
  shipped investment (IR, fab backends, MCP surface, 93% pass-rate), takes the genuinely good ideas, and the
  deterministic critic makes branch-and-prune *cheaper and more exact* than the papers it's borrowed from.
- **Option B — Two-track.** Ludwig-CAD stays the product; spin the Blender deliberative harness up as a
  **separate** experiment/repo (`ludwig-harness`) that shares only the orchestration ideas. *Why:* honors
  the brief's Blender/benchmark thesis without contaminating or stalling the CAD line. Cost: two codebases,
  split focus for a solo project.
- **Option C — Pivot.** Take the brief literally: reorient Ludwig to Blender scene/art generation, VLM-judged,
  benchmarked on BlenderGym/BlenderBench; demote CadQuery to a stub. *Why you might:* the academic frontier
  the brief cites is real and unproductized. Cost: **abandons the shipped CAD core, the fabrication wedge, the
  deterministic-critic thesis, and the MCP traction** — i.e. most of R1–R34 + A1–A7. This contradicts the
  locked direction; only take it as a deliberate, eyes-open bet.

**Recommendation: Option A**, with WS2 as the first buildable slice (it's the strongest transfer, needs no
substrate change, and its acceptance criterion — composite/first-pass at matched budget — is measurable on the
existing eval harness). WS3/WS6 stay out until/unless a vision regime is deliberately reopened.

*De-risking experiment before committing either way:* one WS2 branch-and-prune run on the existing frozen
eval set — (d=3,b=3, critic-pruned) vs current linear codegen, `--eval-repeats 3` — recorded in FINDINGS.
If deterministic-pruned search moves first-pass, that's Option A's thesis proven cheaply on real Ludwig,
with zero Blender risk.
