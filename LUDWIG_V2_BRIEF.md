# LUDWIG_V2_BRIEF.md — The Deliberative Harness

**Version:** 2.0 (locked)
**Date:** 2026-07-06
**Author:** Irgen Salianji (strategy sessions with Claude)
**Executor:** Claude Code
**Status:** Ready for execution. Supersedes the loop-internals sections of `HARNESS_BRIEF.md`; the harness surfaces (MCP server, Agent Skills, memory stores) remain valid but are re-sequenced to Phase 2. `MACOS_APP_PLAN.md` is frozen (not cancelled) until M4.

---

## 0. How to use this brief (instructions to Claude Code)

1. **Audit before building.** Milestone M0 is a read-only audit. Several specs below are written against my *belief* about the current codebase (single-file `ludwig.py`, linear agentic loop, single fixed camera, same-model critic, `results.jsonl` eval output). Where reality differs, write `AUDIT_NOTES.md` and adapt the spec — do not silently deviate.
2. **Every claim must be measurable.** Acceptance criteria are phrased as benchmark deltas or deterministic tests. If a feature can't be measured, flag it rather than shipping it.
3. **Preserve the eval-first culture.** No Tier-1 feature merges without a before/after eval run (`--eval-repeats 3` minimum) recorded in `docs/FINDINGS.md` with a dated entry.
4. **Small PRs, one workstream at a time.** Sequence: M0 → WS0 → WS1 → WS4 → WS2 → WS3 → WS6 → WS5 → WS7. (WS6 benchmark integration lands mid-sequence intentionally, so WS5 improvements are measured on public benchmarks, not only self-eval.)
5. **Ask when a locked decision blocks you; improvise on everything else** within the constraints of §12.

---

## 1. Mission & thesis

Ludwig v2 is a **deliberative, neuro-symbolic design harness**: an agentic system that writes design-as-code (Blender Python today, CadQuery next), *sees* its own output through renders, *searches* over candidate edits with a verifier that prunes, *grounds* spatial precision in deterministic solvers rather than VLM guesswork, and *proves* its quality on public benchmarks instead of self-scored rubrics.

The strategic bet: the academic frontier (BlenderAlchemy → BlenderGym → VIGA/BlenderBench → 3DCodeBench, 2024–2026) has established that (a) verifier compute beats generator compute at scale, (b) interleaved multimodal trajectories beat stateless iteration by large margins, (c) VLMs cannot do precise spatial control and must be paired with symbolic layers, and (d) single-view critique is methodologically broken. No shipped product implements this stack. Ludwig v2 becomes the reference implementation — the productized frontier — and its launch artifact is a benchmark scorecard, not a feature list.

Ludwig's compounding assets, in priority order: (1) the trajectory dataset every run produces, (2) the growing `L_*` skill library, (3) the eval/findings culture as public credibility. The loop itself is *not* a moat; it is table stakes that we must execute better than papers do.

---

## 2. Research grounding (what we adopt, and from where)

| Adopted mechanism | Source | Ludwig v2 implementation |
|---|---|---|
| Verifier-weighted compute; d×b branch-and-prune search | BlenderGym (CVPR 2025) | WS2 Deliberative Search, `veri_ratio` knob |
| Interleaved analysis-by-synthesis with full multimodal trajectory in context | VIGA (2026) | WS1 Trajectory Engine |
| Active viewpoint control; multi-view verification; scene inspection tools | BlenderBench (2026) | WS3 Multi-View Perception |
| Semantically intuitive Action APIs instead of raw bpy | SceneAssistant (2026) — validates existing `L_*` toolkit | WS5 extends `L_*` with relational ops |
| VLMs fail at precise spatial control → symbolic layer required | IR3D-Bench (2025) | WS5 Symbolic Substrate |
| "Imagined" reference images ground abstract language | BlenderAlchemy (ECCV 2024) | WS3.4 Concept Target mode |
| Execution-verified CAD program corpora | BenchCAD (2026) | WS10 print3d (reserved interface) |
| Judge integrity / reward-hacking risk in LLM-as-judge loops | eval-integrity literature (2025–26) | WS4 cross-model judge + honeypots |

Claude Code: read BlenderGym, VIGA, and IR3D-Bench abstracts + method sections before starting WS1–WS3. Cache summaries in `docs/RESEARCH_NOTES.md`.

---

## 3. Non-goals (v2)

- No web UI, no macOS app, no hosted service. CLI + library + (Phase 2) MCP server only.
- No fine-tuning or RL training. We only *collect* trajectories in a training-ready schema (WS7).
- No direct-geometry generation models (Zoo/Backflip style). Code-generation camp only.
- No full print3d domain pack in v2 core milestones — only the substrate interface that guarantees it can plug in (WS10).
- No multi-user features, no auth, no cloud storage.

---

## 4. Architecture overview

```
                        ┌────────────────────────────────────────────┐
                        │              ORCHESTRATOR (WS1)            │
                        │  interleaved trajectory · budget manager   │
                        └───────┬────────────────────────┬───────────┘
                                │                        │
                   ┌────────────▼───────────┐  ┌─────────▼───────────┐
                   │  GENERATOR (existing)  │  │    JUDGE (WS4)      │
                   │  code proposals over   │  │  cross-model VLM    │
                   │  L_* toolkit, k-branch │  │  rubric vN + hooks  │
                   └────────────┬───────────┘  └─────────▲───────────┘
                                │                        │
                   ┌────────────▼────────────────────────┴───────────┐
                   │           DELIBERATIVE SEARCH (WS2)             │
                   │   d×b tree · verifier pruning · veri_ratio      │
                   └────────────┬────────────────────────────────────┘
                                │ candidate programs
                   ┌────────────▼───────────┐
                   │  SYMBOLIC SUBSTRATE     │   deterministic pass on every
                   │  (WS5)                  │   candidate BEFORE VLM judging:
                   │  physics settle ·       │   cheap checks kill bad branches
                   │  collision BVH ·        │   for free
                   │  relational assertions  │
                   └────────────┬───────────┘
                                │ validated programs
                   ┌────────────▼───────────┐      ┌──────────────────────┐
                   │  EXECUTION SANDBOX      │─────▶│ MULTI-VIEW PERCEPTION │
                   │  headless Blender,      │      │ (WS3) view-request    │
                   │  pinned version         │      │ protocol, canonical + │
                   └────────────┬───────────┘      │ judge-requested views  │
                                │                   └──────────┬───────────┘
                   ┌────────────▼──────────────────────────────▼───────────┐
                   │        TELEMETRY / TRAJECTORY STORE (WS7)              │
                   │  run manifest · trajectory JSONL · consented dataset   │
                   └────────────┬───────────────────────────────────────────┘
                                │
                   ┌────────────▼───────────┐
                   │  BENCHMARK RUNNER (WS6) │  BlenderGym · BlenderBench
                   │  PL / N-CLIP / VLM score│  adapters + scorecard report
                   └─────────────────────────┘
```

Substrate abstraction: everything above the Execution Sandbox is substrate-agnostic. `Substrate` is a protocol with two v2 implementations planned: `BlenderSubstrate` (full, v2) and `CadQuerySubstrate` (stub + interface tests only, WS10).

---
## 5. Workstreams — full specifications

### WS0 — Repo restructure & packaging foundation

**Why first:** every subsequent WS touches module boundaries; do the surgery once.

- Convert to a src-layout package. **Locked decision: PyPI/npm-safe name is `ludwig-harness`** (import name `ludwig_harness`; CLI entrypoint remains `ludwig`). The brand stays Ludwig; the package cannot be `ludwig` (owned by the Uber/Linux-Foundation ML framework — verify at execution time and record in AUDIT_NOTES.md).
- Target layout:

```
src/ludwig_harness/
  orchestrator.py        # WS1
  search.py              # WS2
  perception.py          # WS3
  judge/
    __init__.py
    rubrics/             # versioned rubric prompt files: v1.md, v2.md ...
    judges.py            # judge client abstraction (model-agnostic)
    honeypots.py         # WS4.4
  substrate/
    base.py              # Substrate protocol
    blender/             # current L_* toolkit + sandbox runner moves here
    cadquery/            # WS10 stub
  symbolic/
    settle.py            # physics settle
    collision.py         # BVH checks
    relations.py         # assertion DSL
  telemetry/
    schema.py            # pydantic models for all record types
    store.py             # local JSONL/SQLite store
  bench/
    blendergym/          # WS6 adapter
    blenderbench/        # WS6 adapter
  cli.py
tests/
docs/
  FINDINGS.md            # keep; append-only dated entries
  AUDIT_NOTES.md         # M0 output
  RESEARCH_NOTES.md
```

- CI (GitHub Actions): lint (ruff), type-check (mypy, gradual), unit tests, and a headless-Blender smoke job running `ludwig --selftest`. Pin Blender version in one place (`substrate/blender/version.py`); selftest fails loudly on mismatch.
- Preserve full behavior of current CLI during restructure: `ludwig generate`, `--edit`, `--agentic`, `--eval`, `--selftest` must produce identical outputs pre/post (golden-file test on a fixed seed scene).

**Acceptance:** `pipx install .` works; CI green; golden-file parity test passes.

---

### WS1 — Trajectory Engine (interleaved analysis-by-synthesis)

**Problem:** the current agentic loop (believed) re-prompts per turn with summarized state. VIGA-class results require the *full multimodal trajectory* — every render, every critique, every code diff — interleaved in the model's context, so the generator reasons over the history of what it tried and what it saw.

**Spec:**

1. `Trajectory` object: an append-only sequence of typed events:
   - `BriefEvent {text, concept_image?, constraints[]}`
   - `ProposalEvent {branch_id, parent_id, code_diff, rationale}`
   - `SymbolicReport {branch_id, checks[], passed, violations[]}`
   - `RenderEvent {branch_id, view_id, camera_params, image_ref, render_ms}`
   - `JudgeEvent {branch_id, rubric_version, judge_model, scores{axis:score}, critique_text, view_requests[]}`
   - `SelectionEvent {kept_branch, pruned[], reason}`
   - `TerminalEvent {reason: budget|converged|user_stop, final_branch}`
2. **Context assembly policy** (`orchestrator.build_context(trajectory, budget)`): most-recent-first inclusion of full events; images downscaled to a configurable max side (default 768px) for context; when token budget forces truncation, drop *middle* iterations before recent ones, never drop the brief or the last two full iterations. Policy must be a pure function — unit-testable without API calls.
3. Budget manager: hard caps on total model calls, total tokens, total renders per run; exposed as `--budget-calls`, `--budget-renders`. On cap hit → `TerminalEvent(budget)` and return best branch so far. Print a cost estimate line at end of every run (calls × model, renders × avg ms).
4. The generator prompt is rebuilt from the trajectory every turn — no hidden conversational state in the API client. This makes runs resumable: `ludwig resume <run_id>`.

**Acceptance:** on the internal eval set, interleaved-full-context vs current summarized-context, ≥3 repeats: brief-adherence and composite scores must improve or the change is investigated before merge (record either way in FINDINGS). Resume-from-disk produces byte-identical context to an uninterrupted run (deterministic test with a mock model).

---

### WS2 — Deliberative Search (branch-and-prune)

**Problem:** linear refinement is a degenerate search tree. BlenderGym's result: propose-verify-improve with b candidate edits per iteration, verifier-pruned, beats linear at equal compute; at higher budgets, verifier compute dominates.

**Spec:**

1. Search parameters in `ludwig.toml` and CLI:
   - `depth` (d, default 3) — refinement iterations
   - `branch` (b, default 3) — candidate proposals per iteration (temperature-varied and/or prompt-perturbed)
   - `veri_ratio` (default 0.5) — fraction of the *call budget* reserved for judging/pruning vs generating. The scheduler derives effective d and b from the total budget and this ratio.
2. Pruning pipeline per iteration, cheapest first:
   a. **Execution filter** — code runs without error in sandbox (free kill).
   b. **Symbolic filter (WS5)** — deterministic checks; violations either kill the branch (hard assertions) or annotate it (soft warnings passed to the judge).
   c. **Judge tournament (WS4)** — pairwise or list-wise selection of top-k branches from renders. Pairwise comparison is the default (research shows comparative judging is more reliable than absolute scoring); absolute rubric scores are still recorded for telemetry continuity with v1 results.
3. Selection keeps top-1 by default (`--keep-k` for top-k beam). The kept branch's trajectory becomes the parent context for the next iteration's proposals.
4. Determinism hooks: `--seed` fixes proposal temperature seeds and any sampling in perturbation, so search is replayable modulo model nondeterminism.

**Acceptance:** at matched call budgets, (d=3,b=3,veri_ratio=0.5) vs v1 linear (d=9,b=1): composite eval score improves ≥10% on the internal set (3 repeats). If it does not, run the veri_ratio sweep {0.3, 0.5, 0.7} and report the curve in FINDINGS before concluding.

---

### WS3 — Multi-View Perception

**Problem:** single fixed-camera critique reduces 3D judgment to 2D image matching (BlenderBench's core criticism). Occluded garbage passes; spatial errors hide.

**Spec:**

1. **Canonical view set** rendered for every judged branch: hero camera (scene-defined), 3/4 orbit at +120° and +240°, top-down orthographic layout view. Low-res (default 512px) for search iterations; full-res only for the final kept branch.
2. **View-request protocol:** the judge's structured output may include `view_requests: [{type: orbit|closeup|ortho, target_object?, azimuth?, elevation?}]` (max N per iteration, default 2). The orchestrator renders requested views and re-invokes the judge once with them appended. This is the "active scene inspection" loop, bounded.
3. **Cheap programmatic pre-checks per view (before VLM):** subject-fill ratio (hero object bbox area / frame area within configured band), void-frame detection (existing void-guard generalized), horizon/floor-contact heuristic. Failures annotate the branch for the judge rather than auto-kill (viz aesthetics are not decidable).
4. **Concept Target mode (WS3.4):** `--concept auto|<path>|off`. `auto` generates a 2D concept image from the brief via the configured image model at run start; the judge then scores renders *against the concept image* (similarity + deviation critique) in addition to the text brief. Concept image is stored in the trajectory as part of `BriefEvent`. Ship behind a flag; measure before defaulting on.

**Acceptance:** multi-view judging changes the winner vs single-view in a measurable fraction of eval cases (report the disagreement rate — this is the evidence the feature matters); no regression in wall-time beyond 1.6× for the default canonical set at search resolution. Concept mode: brief-adherence axis improves on the eval subset with concrete-visual briefs (3 repeats) or the feature stays flagged.

---

### WS4 — Judge subsystem

**Problem:** same-model self-judging risks systematic self-preference and reward hacking; rubric drift makes historical evals incomparable.

**Spec:**

1. `Judge` abstraction: `judge(brief, concept?, renders[], symbolic_report, rubric_version) -> JudgeEvent`. Model-agnostic client; judge model configured independently of generator (`[judge] model = ...` in ludwig.toml). **Default: judge model ≠ generator model family when two providers are configured; same-family-different-tier otherwise.**
2. **Rubric versioning:** rubric prompts live as files in `judge/rubrics/vN.md`; every JudgeEvent records `rubric_version` and `judge_model`. Eval comparisons across different rubric versions must be refused by the reporting tool unless `--allow-mixed-rubrics`.
3. Structured output contract (JSON schema enforced): per-axis scores (brief_adherence, composition, materials_lighting, technical_integrity), overall pairwise preference when in tournament mode, critique text ≤150 words, optional view_requests, optional `edit_hints[]` (typed suggestions: move/scale/material/lighting — these feed the next generator prompt).
4. **Honeypots (integrity):** the eval suite includes trap cases — e.g., a render pair where one candidate is objectively broken (missing hero object, all-black render) — inserted randomly into judge tournaments during eval runs. Judge integrity metric = honeypot detection rate; reported in every eval summary. If detection <95%, judging config is flagged unreliable.
5. Cross-model comparison experiment (one-off, M2): same-model vs cross-model judge on the internal set, 3 repeats; publish in FINDINGS. This is a publishable/postable result either way.

**Acceptance:** schema-validated judge outputs at 100% (retry-with-repair loop, max 2 repairs); honeypot detection ≥95% with the default config; rubric v2 (rewritten for pairwise + multi-view + symbolic-report input) committed with a changelog entry.

---

### WS5 — Symbolic Substrate (deterministic spatial layer)

**Problem:** VLMs reliably fail precise spatial control (IR3D-Bench). Numeric placement must come from solvers; the VLM commands relations.

**Spec:**

1. **Relational DSL** (extends `L_*`):
   - `L_place(obj, on=surface, align="center|edge|thirds", clearance=0.0)` → computes placement from bounding boxes; optional physics settle.
   - `L_settle(objects=[...], frames=30)` → rigid-body drop + freeze transforms; deterministic seed.
   - `L_assert(relation)` with relations: `on(a,b)`, `above(a,b)`, `inside(a,b)`, `no_collision(group)`, `visible_from(obj, camera)`, `min_gap(a,b,d)`. Assertions evaluate against evaluated scene geometry (BVH via Blender's built-in structures or `mathutils.bvhtree`).
2. **Check pipeline:** after each candidate executes, run all `L_assert`s + a global default set (no interpenetration among named objects; hero object visible from hero camera; all objects above floor plane). Output = `SymbolicReport` (WS1 schema). Hard assertions (user-written) kill the branch; default checks are soft annotations.
3. Generator prompt is updated to *teach* the relational DSL with 3–4 few-shot examples and an explicit instruction: "never compute numeric world coordinates for placement when a relational op exists."
4. All symbolic code runs inside the Blender sandbox process (bpy available); keep it dependency-light — no external physics engine in v2.

**Acceptance:** a new eval axis `technical_integrity` measured programmatically (violation count per scene) drops ≥50% vs v1 on the internal set; unit tests for every relation on synthetic scenes (deterministic, no model calls); documented DSL page in docs.

---

### WS6 — Benchmark integration (the launch artifact)

**Problem:** self-referential evaluation. The credibility move is public numbers.

**Spec:**

1. `ludwig bench blendergym --tasks <subset|all> --config <profile>` — adapter that: loads BlenderGym task instances (start scene script + goal images), runs the Ludwig pipeline in goal-image mode (this is Concept Target mode with a provided image — reuse WS3.4), and computes the benchmark's official metrics: **photometric loss (PL)** and **negative CLIP similarity (N-CLIP)**, plus our judge score as auxiliary. Use the benchmark's official scoring code where licensing allows; vendor it under `bench/` with attribution, else reimplement to published spec and validate against reported baseline numbers.
2. `ludwig bench blenderbench ...` — same pattern; note BlenderBench requires viewpoint control and scene inspection, which WS3 provides. If the harness cannot yet complete a task category, report it as unsupported rather than scoring zero silently.
3. **Scorecard report:** `ludwig bench report` renders a markdown scorecard (per-task-family PL/N-CLIP/VLM-score, config profile, cost, wall time, honeypot integrity) → `docs/BENCHMARKS.md`. This file is the launch post's core content.
4. Budget guardrails: bench runs print projected API cost before starting and require `--yes` above a configurable threshold.

**Acceptance:** full BlenderGym run completes on at least the blend-shape and lighting task families with metrics within sanity range of published baselines for comparable setups; `docs/BENCHMARKS.md` generated; a `bench-repro.md` documents exact commands + config hash for reproduction.

---

### WS7 — Telemetry & trajectory dataset

**Problem:** trajectories are the compounding asset; v1 discards most of the information each run produces.

**Spec:**

1. Every run writes a **run manifest** (`runs/<run_id>/manifest.json`): config hash, model versions, rubric version, substrate + Blender version, seed, budgets, git commit of ludwig itself.
2. Full trajectory persisted as JSONL (`runs/<run_id>/trajectory.jsonl`) using the WS1 event schema; images stored content-addressed (`runs/<run_id>/media/<sha>.png`) and referenced by hash. Schema version field on every record; pydantic models in `telemetry/schema.py` are the single source of truth.
3. **Consent & dataset export:** telemetry is local-only by default. `ludwig dataset export` packages selected runs into a training-ready format (brief → code-diff sequence → renders → judge signals) with a manifest of licenses/consent flags. No network upload code in v2 at all — export produces a local archive only.
4. Retention: `ludwig runs prune --keep-last N --keep-starred`.

**Acceptance:** a fixed-seed mock-model run produces a trajectory that replays (`ludwig replay <run_id>`) to identical SelectionEvents; schema round-trip tests; export archive validates against its own manifest.

---

### WS8 — Skill library learning (Phase 2, design-only in v2)

Mine successful trajectories for recurring code motifs → propose new `L_*` helper candidates (DreamCoder-style compression, human-approved before entering the toolkit). **v2 deliverable is a design doc + the telemetry hooks needed later** (WS7 already captures code diffs + outcomes; add a `motif_tags` optional field to ProposalEvent). No implementation in v2 core.

### WS9 — Surfaces: MCP server + Agent Skill (Phase 2, thin)

After M3, wrap the orchestrator as (a) an MCP server exposing `generate`, `refine`, `critique`, `bench_status` tools and (b) a Claude Code Agent Skill (SKILL.md) that teaches invocation of the CLI. Keep both thin — no logic outside the core library. Publication to registries happens with the benchmark scorecard, not before.

### WS10 — CadQuery substrate stub (interface guarantee)

`substrate/cadquery/` implements the `Substrate` protocol signatures with `NotImplementedError` bodies plus **one** working end-to-end path: brief → CadQuery code → STL export → deterministic geometric checks (watertight, min wall thickness via trimesh) on a single canonical part (a bracket). Purpose: prove the abstraction holds for B-rep before the print3d pack is built; BenchCAD is noted as the future eval corpus. **Acceptance:** the bracket path passes in CI without Blender.

---

## 6. Configuration surface (ludwig.toml)

```toml
[models]
generator = "claude-sonnet-4-6"        # BYO principle preserved
judge     = "<different family/tier>"  # WS4 default rule
concept   = "<image model>"            # optional, WS3.4

[search]
depth = 3
branch = 3
veri_ratio = 0.5
keep_k = 1
seed = 0

[budget]
max_calls = 60
max_renders = 120
cost_confirm_usd = 5.0

[perception]
canonical_views = ["hero", "orbit120", "orbit240", "top_ortho"]
search_res = 512
final_res = 1920
max_view_requests = 2

[telemetry]
enabled = true
runs_dir = "runs"
```

CLI mirrors every key (`--depth`, `--veri-ratio`, ...). Config hash of the resolved config goes into the run manifest.

---

## 7. Milestones & acceptance gates

| Milestone | Content | Gate |
|---|---|---|
| **M0 — Audit** (≤2 days) | Read-only codebase audit vs this brief's assumptions; `AUDIT_NOTES.md`; verify PyPI name availability; golden-file baseline captured | AUDIT_NOTES reviewed by Irgen |
| **M1 — Restructure** | WS0 complete | CI green, golden parity, `pipx install` |
| **M2 — Deliberative core** | WS1 + WS4 + WS2 | Interleaved≥summarized (FINDINGS entry); honeypots ≥95%; search ≥10% at matched budget (or documented sweep) |
| **M3 — Perception & benchmarks** | WS3 + WS6 | BlenderGym scorecard in `docs/BENCHMARKS.md`; disagreement-rate report for multi-view |
| **M4 — Grounding & telemetry** | WS5 + WS7 + WS10 stub | Integrity violations −50%; replay determinism; bracket path in CI |
| **M5 — Surfaces & launch** (Phase 2) | WS9, registry publication, launch post from BENCHMARKS.md | Public release |

Each milestone ends with: FINDINGS entry, version tag, and a ≤1-page status note to Irgen listing deviations from spec.

---

## 8. Testing strategy

- **No-model tests** (fast, CI-default): context assembly policy, search scheduler math, symbolic relations on synthetic scenes, schema round-trips, replay determinism with a scripted mock model.
- **Model-in-the-loop tests** (manual/`make eval`): internal eval set with `--eval-repeats 3`; honeypot integrity; benchmark subsets.
- **Sandbox tests:** headless Blender smoke on pinned version; a matrix job on Blender N and N+1 that is *allowed to fail* but reports API drift early.

---

## 9. Risks & mitigations

1. **API cost explosion from search × multi-view.** Mitigation: budget manager is built in M2 before WS3; search-res renders; pairwise judging on downscaled images; cost line on every run.
2. **Benchmark scoring mismatch** (our reimplementation vs official). Mitigation: validate against published baseline numbers before publishing ours; document any divergence.
3. **Blender API drift** (v5.x). Mitigation: pinned version, drift matrix job, version check in selftest.
4. **Judge gaming / inflated self-eval.** Mitigation: honeypots, cross-model default, pairwise-not-absolute in tournaments, symbolic hard checks that no VLM can charm.
5. **Scope creep toward the harness surfaces.** Mitigation: WS9 is gated behind M3's scorecard; the launch is the scorecard.
6. **My codebase assumptions are wrong.** Mitigation: M0 audit is a hard gate; spec adapts via AUDIT_NOTES, not silent deviation.

---

## 10. Locked decisions

- D1: Package name `ludwig-harness`; brand remains Ludwig. (Verify availability in M0.)
- D2: Code-generation camp; no direct-geometry models in core.
- D3: Judge ≠ generator by default; rubric files versioned; mixed-rubric comparisons refused.
- D4: Search defaults d=3, b=3, veri_ratio=0.5; pairwise tournament judging.
- D5: Canonical 4-view set; view-request protocol capped at 2/iteration.
- D6: Telemetry local-only; export is offline archive; no upload code in v2.
- D7: Launch artifact = benchmark scorecard (M3), not feature announcement.
- D8: Conservative/Hybrid/Full dial maps to: Conservative = single iteration + report only; Hybrid = search with human selection at each SelectionEvent (`--interactive`); Full = autonomous to TerminalEvent. Implement the dial as orchestrator policy, not three code paths.

## 11. Open decisions (for Irgen, non-blocking)

- O1: Which second model provider for the cross-model judge default.
- O2: Concept-image model choice for WS3.4 `auto` mode.
- O3: Whether M5 launch includes the Show HN post or conference-first.
- O4: License confirmation (assume Apache-2.0 core unless stated otherwise).

## 12. Style & engineering constraints for Claude Code

Python ≥3.11; ruff + mypy clean on new modules; pydantic v2 for all schemas; no new heavyweight deps without a FINDINGS-style justification (trimesh allowed for WS10; nothing GPU-bound); every public function docstringed; docs updated in the same PR as code; commit messages reference WS/M IDs.

---

*End of brief. Ludwig v2 is judged by one sentence: "the deliberative harness — it searches, it looks from every angle, it proves it on the benchmark."*
