# Changelog

All notable changes to Ludwig are documented here.

## [Unreleased]

### Added
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
