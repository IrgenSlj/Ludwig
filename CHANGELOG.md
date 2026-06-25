# Changelog

All notable changes to Ludwig are documented here.

## [Unreleased]

### Added — P0/S5 (STEP backend — the fabrication deliverable)
- `backends/step.py`: OCCT STEP export + a round-trip helper (re-read through OCCT to prove the file is
  valid, openable geometry). It is a fabrication export, gated by a pre-export critic hook (BRIEF §5).
- `cli.py "<prompt>"` now writes `out/<id>.py` (the recipe / source of truth) and `out/<id>.step`, and
  withholds the STEP if the critic isn't all-pass. `--selftest` round-trips the bracket STEP (11/11).
- Verified live: a prompt produced a valid 25 KB ISO-10303-21 STEP file.

### Added — P0/S4 (the deterministic critic panel)
- `critic/`: `geometric` (OCCT manifold/watertight via BRepCheck), `dimensional` (named-dim exact, 1e-6),
  `semantic` (units present, no orphan geometry, declared hole count), aggregated by a `critic.panel`
  registry. The loop calls the panel and stays panel-agnostic — adding a critic is `register(...)`, not a
  loop change ([H4], BRIEF §0 gate).
- `cli.py --eval --live --repair`: measures the post-repair pass-rate (the full loop + panel).
- **Headline: live post-repair geometric pass-rate 100% (5/5) vs 60% first-pass** — the deterministic
  critic's exact signal lets repair close the gap (docs/FINDINGS.md). 55 tests pass.

### Added — P0/S3 (the generate→execute→repair loop, live)
- `agent/loop.py`: the compiler driver on the provider-blind seam — `generate` (codegen) → `execute`
  (exec the program, force the OCCT build so `StdFail_NotDone` surfaces) → `verify` (provisional;
  the real critic panel is S4) → `repair`. `Brief`/`LoopResult`, fence-stripping, minimal prompt stack.
- `cli.py "<prompt>"` compiles live via `claude`; `--eval --live` measures the real first-pass rate.
- `eval/llm.py`: first-pass LLM builder for the pass-rate harness.
- **First real first-pass geometric pass-rate: 60% (3/5)** — confirms [H1] empirically (docs/FINDINGS.md).
- Loop tests run token-free via mocked inference; 49 tests pass.

### Added — P0/S2 (IR core · geometry service · pass-rate instrument)
- Real OCCT exact B-rep via **CadQuery** behind the lazy `GeometryService` (box/hole/bbox/validity).
- Thin element-API (`toolkit`: part/box/hole/clearance_hole) that registers named dims; `standards.yaml`
  loader resolves domain semantics (M8 clearance → ⌀9.0), never guessed in codegen.
- The `eval/` **first-pass geometric pass-rate** harness ([H6]) over a frozen 5-brief held-out set, with a
  deterministic reference oracle (replaced by LLM codegen in S3). `cli.py --eval` reports the number.
- `cli.py --selftest` now runs the bracket geometry gate (80×40×6 exact, two holes, valid solid) when the
  kernel is present; stays green without it. CI installs cadquery and runs the gate + eval.

### Changed — Re-foundation (mesh → precision CAD/BIM compiler)
- Pivoted from a mesh render tool to an AI-native precision CAD/BIM **compiler**: a typed semantic
  IR (the truth) over OCCT/CadQuery, a deterministic critic, and derived backends (STEP/IFC/drawing/
  render/present). See `BRIEF.md` (founding architecture), `docs/ROADMAP_SESSIONS.md`, `docs/UX_BRIEF.md`.
- New skeleton: `ir/ geometry/ backends/ critic/ agent/ toolkit/ prompts/ store/ standards.yaml cli.py`.
- Salvaged: the provider-blind inference seam (`agent/inference.py`) and the `L_*` render toolkit
  (`backends/render_toolkit.py`, for the P1 render backend).
- Removed the mesh-substrate / wrong-shell scaffolding (the M0–M4 daemon, Next.js web, Blender adapter,
  vision-critic-as-primary). The mesh era is preserved at the git tag **`mesh-era-m4`**.

### Added
- **Core loop**: prompt → Claude writes Blender Python → headless render →
- **Core loop**: prompt → Claude writes Blender Python → headless render →
  Claude vision-critiques the render → iterate.
- **Judge panel**: N diverse candidates per round, scored on a 5-axis rubric
  (framing, lighting, materials, brief-coverage, believability), score-gated
  across rounds.
- **Realism toolkit** (`ludwig_blender_lib.py`): procedural PBR materials,
  balanced lighting presets, a studio set (seamless sweep backdrop + 3-point
  rig), and bounding-box auto-framing.
- **`--edit`**: surgically re-prompt an existing scene ("same, but taller / in
  brass") — the design-as-code editability moat.
- **`--quick`**: fast single-shot mode (1 candidate, 1 round) for iterating.
- Cycles "hero shot" re-render of the winning scene.
- Inference via the local `claude` CLI (no API key); cross-platform Blender
  detection; retrying inference with backoff; preflight checks.
- Smoke tests and CI.

### Added (post-v0)
- **`L_asset` + `--assets`** — retrieve real CC0 Poly Haven meshes (no API key)
  and arrange them, with a primitive fallback when no asset matches. Measured to
  *lose* on steerable subjects (loses brief-adherence) — best reserved for
  props/context. See [docs/FINDINGS.md](docs/FINDINGS.md).
- **`--eval-repeats N`** — average N generations per brief to cut the large
  per-brief noise, so small mode deltas are actually resolvable.
- **Agentic refinement hardening** — a broken refinement gets one error-fed-back
  repair (keeping the refinement intent); refinements that render an empty/void
  frame are rejected rather than promoted.
- **[docs/FINDINGS.md](docs/FINDINGS.md)** — the measured research log (critic
  reliability, the brief-adherence ceiling, retrieval vs. steerability, agentic).
- **Eval harness (`--eval`)** — a frozen brief suite, each run as one isolated
  candidate and scored by the validated critic, with history appended to
  `eval/results.jsonl` (mean + per-axis means + per-brief scores). Prints the
  A/B delta vs the most recent run of the *other* mode, so "does `--agentic`
  actually beat one-shot?" becomes a measured number, not a claim. Composes with
  `--agentic` / `--model` / `--provider`.
- **Agentic worker (`--agentic`)** — instead of a stateless one-shot, each
  candidate now runs a self-correcting loop: the model *views its own render*
  with its Read tool, judges it like an art director, and returns an improved
  script — repeating until it replies `DONE` or `--agent-turns` is hit. The
  external rubric critic still gates rounds (so scoring stays consistent), and
  rendering stays in Ludwig's controlled path. Works on any vision-capable
  provider; `--model` selects the brain (e.g. `opus`).
- **Pluggable inference (`--provider`)** — Ludwig is no longer wired to a single
  vendor. `claude` (default) keeps best-in-class intelligence with zero API key;
  `--provider opencode` routes through opencode's headless `run` so users can
  bring ANY model (Anthropic/OpenAI/Gemini/OpenRouter) or a FREE local model via
  Ollama (`$LUDWIG_MODEL=ollama/...`). The orchestrator stays provider-blind.
- **Per-candidate fault isolation** — an inference failure (provider down,
  model unauthenticated, timeout) now fails just that candidate instead of
  crashing the whole panel/run.
- **`L_seat(*objs)`** toolkit helper — drops a mesh, or a whole assembly while
  preserving relative positions, onto the floor (z=0). Directly attacks the
  critic's most frequent complaint after bad crops: subjects that float or sink.
  Wired into the codegen + edit briefs so the model uses it.
- **`--selftest`** — one command that verifies the whole stack (pure-Python unit
  suite + a real Blender render through the toolkit, asserting L_seat grounds the
  subject and the frame isn't void) in ~2s, spending zero claude tokens. Exits
  non-zero on failure, so it doubles as a CI gate.

### Fixed
- **Render timeouts no longer crash the run.** A slow Cycles hero render that
  exceeded the subprocess budget raised an uncaught `TimeoutExpired`, killing the
  whole pipeline *after* all the codegen/critique work. `render()` now catches it
  and reports a normal render failure (hero renders also get a 600s budget).
- **Stale renders can no longer mask a failed render.** Because Blender exits 0
  even when a script raises, file-existence is the success signal — but a leftover
  PNG from a previous run reusing the same slug could falsely pass. `render()` now
  removes any existing output first, so the file reflects the current run.
- `--edit` now reports honestly when the hero re-render fails instead of always
  printing success.
- Preflight prints a non-fatal note when Pillow is missing (void-frame detection
  is disabled, so empty renders would otherwise silently cost a critique call).

### Known limitations
- Geometry is primitive-assembled — strongest on hero objects / product renders;
  complex multi-object interiors are still crude. Richer geometry helpers are on
  the roadmap.
- The critic is a tough grader; scores are a relative signal, not an absolute one.
