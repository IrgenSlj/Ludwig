# V2_ROADMAP.md — Ludwig v2: the deliberative harness on the CAD core

**Lead roadmap.** [LUDWIG_V2_BRIEF.md](../LUDWIG_V2_BRIEF.md) is now the driving document; this file is its
execution plan, adapted through the **M0 decision (Option A — retrofit onto the CadQuery/OCCT core)**
recorded in [AUDIT_NOTES.md](AUDIT_NOTES.md) + [FINDINGS.md](FINDINGS.md). The founding
[BRIEF.md](../BRIEF.md) still governs the **locked substrate + critic decisions** (CadQuery/OCCT is the
geometry service; the IR is the truth; the critic is deterministic-first, vision demoted). The v2 brief
leads on the **harness mechanisms** (search, trajectory, judge, symbolic, benchmark, telemetry); it does
**not** get to reintroduce Blender, a VLM-centered judge, or Blender scene benchmarks — those reverse
locked decisions and were rejected at M0.

*Last updated 2026-07-06. One WS-slice per commit; push often; `--selftest` green every step; ship to main.*

---

## 1. The thesis, kept honest for a CAD substrate

The v2 brief's five research bets, and how each lands on Ludwig (not Blender):

| Brief bet | On the CAD core |
|---|---|
| Verifier compute beats generator compute (BlenderGym) | **Sharper here** — our verifier is the *deterministic* critic: free and exact. We prune harder for zero model cost. (WS2) |
| Interleaved full trajectory beats summarized iteration (VIGA) | Full repair context = every code diff + every critic report in the loop's context, not a one-line summary. (WS1) |
| VLMs fail at precise spatial control → need a symbolic layer (IR3D-Bench) | **Already shipped** — this is Ludwig's founding thesis (exact B-rep + deterministic critic). WS5 only *extends* it with a relational assertion surface. |
| Judge integrity: cross-model, pairwise, honeypots | Applies to the **one demoted aesthetic pass** only; the geometric critic can't reward-hack. WS4 is mostly structured-record + rubric versioning discipline. |
| Prove it on a public benchmark, not self-eval | **CAD** benchmark (BenchCAD / Query2CAD / CAD-Coder family), not BlenderGym. First-pass geometric correctness + execution success are the CAD-native metrics. (WS6) |

Compounding assets (brief §1), unchanged: (1) the **trajectory dataset** every run produces (WS7),
(2) the growing **toolkit** of element-API ops (WS8, design-only), (3) the **eval/FINDINGS culture** as
public credibility (WS6 scorecard).

## 2. Workstream adaptation map (brief → CAD)

| WS | Brief (Blender) | Ludwig v2 (CAD) | Transfer |
|---|---|---|---|
| WS0 | src-layout rename to `ludwig_harness` | **Repo prep, not rename**: config surface (`ludwig.toml`) + harness module skeleton + telemetry scaffolding. No risky 10k-LOC rename; name reserved only. | scoped-down |
| WS1 | interleave renders+critiques in context | interleave **code diffs + deterministic critic reports** in the repair context; resumable runs | concept |
| WS2 | d×b branch-and-prune, VLM-pruned, `veri_ratio` | d×b branch-and-prune, **critic-pruned (free)**; `veri_ratio` = explore-vs-refine budget split (verification is free, so it re-tunes) | **strong** |
| WS3 | multi-view VLM perception, concept image | **CAD canonical projections** (existing HLR/section/drawing backends) as multi-view + programmatic pre-checks; **no VLM**. Low priority. | weak/analog |
| WS4 | cross-model VLM judge, rubrics, honeypots | structured critic/judge **record** + rubric versioning; cross-model + pairwise **only for the demoted aesthetic pass** | partial |
| WS5 | physics settle, BVH, relational DSL | **relational assertion surface** over exact B-rep (`assert on/above/inside/no_collision/min_gap`); most checks already exist in the critic panel | concept (mostly done) |
| WS6 | BlenderGym / BlenderBench | **CAD benchmark adapter** (BenchCAD / Query2CAD-style) → public scorecard = the launch artifact | re-targeted |
| WS7 | run manifest + trajectory JSONL + replay | same, verbatim — substrate-agnostic | **strong** |
| WS8 | mine `L_*` motifs (design-only) | mine **toolkit** op motifs (design-only); telemetry hook only | concept |
| WS9 | MCP server + Agent Skill (Phase 2) | **MCP already shipped (A2–A4)**; extend + add SKILL.md; publish with the scorecard | mostly done |
| WS10 | CadQuery substrate stub | **inverted** — CadQuery is the core. WS10 = formalize the `Substrate` protocol so a *second* engine (build123d/mesh) could plug; keep the STL/print path as the canonical E2E | re-scoped |

Legend: **strong** = build as-is · concept = the idea transfers, implementation differs · partial/analog/weak = limited ·
re-targeted/re-scoped/inverted = the brief's framing was wrong for CAD and is corrected here.

## 3. Sequence & milestones (adapted from brief §7)

Ordered by leverage and dependency, not the brief's literal order (which front-loads Blender-specific WS3/WS6).

| Milestone | Content | Gate (measurable) | State |
|---|---|---|---|
| **M0 — Audit** | AUDIT_NOTES + Option-A decision | reviewed by Irgen | ✅ done |
| **M1 — Repo prep** | `ludwig.toml` config surface + resolver + config hash; harness module skeleton (`agent/search.py`, `telemetry/`); RESEARCH_NOTES cached | `--selftest` green; config round-trips; CLI back-compat | ← next |
| **M2 — Deliberative core** | **WS2** search + **WS7** telemetry + **WS1** trajectory context | WS2: critic-pruned d×b ≥ linear at matched call budget on the frozen set (`--eval-repeats 3`), FINDINGS entry; WS7: replay determinism (mock model) | |
| **M3 — Judge & symbolic** | **WS4** structured record + rubric versioning; **WS5** relational assertion surface | WS4: schema-valid records 100%, rubric vN committed; WS5: relational assertions unit-tested on synthetic parts, a brief that needs one passes | |
| **M4 — Benchmark & scorecard** | **WS6** CAD benchmark adapter → `docs/BENCHMARKS.md`; **WS3** programmatic multi-view pre-checks | WS6: a public CAD benchmark subset runs end-to-end, metrics within sanity of published baselines; scorecard generated | |
| **M5 — Substrate & surfaces** | **WS10** `Substrate` protocol; **WS9** SKILL.md + MCP extensions; launch from BENCHMARKS.md | protocol has ≥1 real impl (CadQuery) + interface tests; registry publish | |

Each milestone ends with: a FINDINGS entry, a git tag, and a ≤1-page note of deviations from the brief.

## 4. Config surface (`ludwig.toml`, CAD-adapted from brief §6)

Harness runtime knobs live in a new `ludwig.toml` (stdlib `tomllib`, read-only, dependency-light).
Domain standards + **inference tiers stay in `standards.yaml`** (already working — not relitigated).
Blender-only keys from the brief (`canonical_views`, render res) are dropped.

```toml
[search]
depth = 3          # d — refinement iterations
branch = 3         # b — candidate proposals per iteration
keep_k = 1         # beam width
veri_ratio = 0.5   # explore↔refine budget split (verification is free here)
seed = 0

[budget]
max_calls = 60     # hard cap on model calls per run → TerminalEvent(budget), return best-so-far
cost_confirm_usd = 5.0

[telemetry]
enabled = true
runs_dir = "runs"
```

The resolved config's **hash** goes into every run manifest (WS7). CLI mirrors every key
(`--depth`, `--branch`, `--veri-ratio`, `--seed`, `--budget-calls`).

## 5. Engineering constraints (brief §12, reconciled with Ludwig's spine)

- **Dependency-light spine.** Heavy deps stay lazy. The brief mandates pydantic v2 for schemas; we use it
  **only in `telemetry/` (WS7), imported lazily** — never in the `--selftest` hot path. Search config is a
  plain dataclass (matches `Brief`/`LoopResult`). Rationale logged in FINDINGS; keeps selftest green without
  pydantic installed. `trimesh` allowed for geometric checks (already a printability dep path).
- **Eval-first.** No Tier-1 feature merges without a before/after `--eval-repeats 3` run in FINDINGS.
- **Token-free gate.** `--selftest` stays the pure-Python regression gate; every WS ships no-model tests
  (scheduler math, replay determinism via scripted mock model, relational assertions on synthetic scenes).
- **Contracts, not loop edits.** New critic/backend/substrate registers without touching the loop ([H4]).
- **Back-compat.** Every new capability is opt-in (flag/config); the default `cli.py "<prompt>"` path is
  byte-unchanged until a measured win flips a default.
- **Ship to main, push often, delegate** parallelizable work (research, review passes, test authoring).

## 6. Open decisions (brief §11 — non-blocking, for Irgen)
- O1: second model provider for the cross-model aesthetic judge (WS4) — only matters if we keep the aesthetic pass.
- O2: **RESOLVED (from [RESEARCH_NOTES.md](RESEARCH_NOTES.md)) — launch on BenchCAD** (execution-verified,
  CadQuery/OCCT-native, CC-BY-4.0/MIT, has an instruction-edit task matching `--edit`), with **Text2CAD-Bench**
  as the curated hard-geometry companion. Headline metric pair: **valid-solid/execution rate + IoU**, reported
  **first-pass vs after-repair**. Reject Query2CAD/Fusion360 for the public scorecard; keep CADSmith as an
  internal regression harness. *Caveat: verify the exact arXiv IDs + baseline numbers before WS6 builds (M4) —
  the research flagged some source figures as future-dated/unverified.*
- O3: whether WS3 CAD multi-view pre-checks are worth building at all (no VLM ⇒ marginal); default = defer.
- O4: license — assume Apache-2.0 core unless stated (brief O4).
