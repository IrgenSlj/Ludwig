# Changelog

All notable changes to Ludwig are documented here.

## [Unreleased]

### Added — the agentic harness (A-series) + macOS embed prep (D-series) + Studio v2
- **The wire contract (A1).** Every result payload carries `schema_version`, stamped at the service layer
  so HTTP, SSE, MCP, CLI and tests agree. `docs/CONTRACT.md` documents the result payload, the critic
  report, the Op schema, the SSE events, and the versioning policy. Plan of record repointed to the
  A-series (`HARNESS_BRIEF.md`) + D-series (`docs/MACOS_APP_PLAN.md`); R1–R34 marked complete/historical.
- **MCP server (A2).** `cli.py mcp` (`agent/mcp.py`, FastMCP, lazy SDK) exposes `ludwig_compile` /
  `ludwig_verify` / `ludwig_build` / `ludwig_export` — any harness drives Ludwig. Every result carries the
  critic verdict; export refuses on a failing critic (the pre-export gate is inside the tool). One daemon,
  one payload shape, many clients — the tools back onto the same `webapp.service` the Studio uses.
- **A4 — the demo, the docs, the second number.** A *runnable* trust-story proof
  (`examples/mcp_walkthrough.py`) spawns the real stdio MCP server and drives the whole arc — verify →
  agent param-edit op + its inverse → **reject** a `RunShell "rm -rf /"` op (nothing executes) → critic
  catches a 0.5 mm-wall fabrication defect → **export refused** on the failing critic → confirmed export
  writes a verified STEP — asserting each invariant (exit ≠ 0 if any breaks), token-free. `docs/MCP.md`
  now leads with the one command. The `--eval --mcp` external-agent harness is hardened against inference
  throttling (paces between briefs + retries only throttle-shaped failures with real backoff; genuine
  geometry misses are never retried), and the inference seam backs off longer on rate-limit stderr so a
  transient limit self-heals. Result: **external-agent pass-rate 93% (14/15) — the gap to the native
  first-pass rate is 0** (the §8 harness thesis, quantified; the clean run needed zero retries). FINDINGS +
  STATUS updated with the honest number.
- **Repair corpus infra (A5).** `store/repairs.py` — remembered (critic-failure → fix) pairs, keyed on a
  normalized failure signature (base check-names / build-error class), ranked by overlap, rendered to repair
  as a minimal diff. Mined from `eval/pool.py` (disjoint from the frozen set — no train-on-test) via
  `cli.py --mine-repairs`; injected into the repair prompt when `memory.repair_corpus` is on. **Default OFF
  and unmeasured** — flips default-on only if an on/off frozen-set eval moves repair rounds/rate. Byte-for-byte
  the original loop when off. 4 selftest anchors.
- **Public-demo runtime verified (A4 follow-up).** Drove the demo end-to-end as the container runs it
  (`LUDWIG_DEMO=1 --serve`): token-free adopt → verified STEP/IFC + a live mass/cost estimate, all safety
  gates holding (generation refused; arbitrary programs rejected). Recorded in `DEPLOY.md` — the GTM "demo is
  done" claim is now backed by a check.

### Changed — critic hardening + plumbing cleanup
- **Dimensional check self-verifies registered extents.** With no brief-declared dims (gallery seeds, adopt,
  bare compile), the dimensional critic now checks the element's own registered extent dims against the
  measured solid instead of reporting a vacuous `no declared dims` n/a — so the headline check runs green
  (the Studio bracket now shows dimensional verified), and any op that desyncs a registered extent is caught.
  Brief-declared paths are unchanged.
- **MCP `ludwig_export` no longer builds twice.** It executed + ran the full critic panel, then re-executed
  and re-verified the same solid before writing. Factored `service.execute_and_verify` + `verify_payload`;
  export now builds once and writes from the same `(el, crit)` — roughly halved export latency. `verify_to_result`
  and `build_to_result` share the helper.

### Removed — inert scaffolding off the current direction (recoverable at tag `mesh-era-m4`)
- **The Blender render backend** (`backends/render.py` + `backends/render_toolkit.py`, ~535 lines): an
  unimplemented, never-registered stub for the artist/render vertical (an explicit A-series non-goal).
- **`store/db.py`** — the project/run/artifact SQLite stub (BRIEF §4) with zero writers, superseded by the
  measured memory stores (`store/repairs.py`); `store/` is now the memory-stores home.
- **4 dead `standards.yaml` keys** (`units.assert_units`, `tolerances.angular`, `manufacturing.default_material`,
  `drawing.hlr_algorithm` — a documented toggle that read nowhere). Every remaining key is consumed.
- **Dead code**: `Critique.repair_hints()` was unused and duplicated inline in the repair path (loop now calls
  it); a dead local in the dimensional critic.

- **Op-API over MCP + the permission gate (A3).** `ludwig_build` applies agent-supplied ops as DATA
  (malformed → rejected, nothing exec'd) and returns an inverse plan for undo. A `permissions` block in
  `standards.yaml` (`agent/permissions.py`, mode auto/plan/locked + per-class rules) is enforced in the one
  shared write path (`build_from_ops`) — headless-correct: "confirm" is an explicit re-call, not a dialog.
  The Studio's permission mode-dial (`/api/permissions`) governs the local hands to match.
- **Daemon hardening for embedding (D1).** `/api/health`, `/api/shutdown`, `--port 0` (ephemeral, prints
  `PORT=`), and a loopback session `--token` guarding `/api/*` + `/out/*` — the surface the macOS shell and
  MCP embed. Open by default (back-compat).
- **Studio v2 (design).** The Studio moved from a cockpit to the viewfinder: full-bleed Stage, floating
  glass panels, a ⌘K intent bar, two calm themes, and the permission dial — engine wiring unchanged. The
  disconnected `prototype/` mock was retired; `/` now serves the Studio.

### Fixed — bare-prompt critic coverage: dims + hole-count extraction
- A live/inline compile (`cli.py "<prompt>"`, webapp) auto-extracts named dims and the hole count from
  the prompt so the deterministic critic verifies them. Three latent bugs left that coverage empty:
  the dim regex captured only 2 of 3 extents (`A × B × C` → `{}`); the hole regex read the thread size
  as the count (`two M8 holes` → 8); and the word-count path used a non-capturing group with `group(1)`
  (dead, masked by the M8 bug). Now `80 × 40 × 6 … two M8 clearance holes` → dims {80,40,6}, holes 2 —
  the headline dimensional check actually runs on live compiles. Frozen-set eval unchanged (100%).

### Fixed — live model tiering (codegen/critic) was passing tier LABELS as model names
- `agent.loop._tier_model` resolved `standards.yaml: inference.codegen_tier` ("cheap") / `critic_tier`
  ("best") to the literal label and passed it to `--model`, which the `claude` CLI rejects ("model
  'cheap' may not exist") — so every live compile failed/retried for minutes. Labels now resolve
  through a new `inference.tiers` map (cheap→haiku, best→opus); an unmapped label falls back to the
  provider default, never a literal. Live compile works again (haiku codegen, opus repair).

### Added — P3 application (the Stage & Director — webapp)
- **DRAWING representation** on the Stage: the rep-switcher now shows the real conventioned shop-drawing
  sheet (PNG) alongside 3D / elevation / program; DXF + the presentation sheet added to deliverables.
- **`backends/present.py`** — presentation auto-assembly: a self-contained HTML one-pager composing the
  derived views (title block, embedded drawing, dimension schedule, deliverables) in the house style.
- **Ambient Correctness** — the deterministic critic painted onto the geometry: each solid carries a
  subtle wash of its critic colour (teal-green verified / amber below-spec / red fail), brighter on
  selection. `service` now carries `element_id` + `severity` per check. "The moat made visible."
- **Point-to-Navigate** — click a solid on the Stage → its program node highlights, params surface,
  provenance updates; a raycast resolves the pick to a program node by lineage, never a kernel handle
  ([H2]). Completes the bidirectional Stage↔program link.
- **Activity Rail** — the agent's work streamed live (Server-Sent Events): `loop.run(on_event=…)` emits
  codegen → execute → critic → repair stages, `service` adds a per-backend derive stage, `server` exposes
  `/api/compile_stream`; the Stage paints a running/done/failed rail with a Cancel control. Falls back to
  the non-streaming POST. on_event never changes loop behavior (a throwing sink is swallowed).
- **Exploration contact-sheet** — "branches are cheap": Explore generates N first-pass variants
  (`/api/explore`), ranks them by the deterministic critic, and fans the Stage into a contact sheet of 3D
  thumbnails (one offscreen renderer); adopting one re-executes it token-free and derives (`/api/adopt`).
- Verified live in-browser end to end (haiku codegen). selftest 14/14, 92 tests, ruff clean.

### Added — P2 (conventioned shop-drawing engine — the moat) · closes the P1 shop-drawing gate
- `backends/shopdrawing.py`: a real conventioned shop drawing — a **third-angle multi-view** sheet
  (front elevation / plan / side), scale-aware (picks the scale that best fills the sheet; enlarges
  small parts, reduces large ones), with the conventioned layer hierarchy (visible / hidden / centre-
  line / dimension / border), **dimensions with witness lines + arrows** whose text reads TRUE mm via
  `DIMLFAC` regardless of plot scale, hole/anchor **feature overlay** (circle + centre-cross in plan,
  dashed hidden walls + centre-line in the elevations), grouped **callouts** (`2× ⌀9 (M8) THRU`), a
  general-notes block, and a **title block** (part, type, material, scale, size, dwg id). Emits a
  rendered **PNG preview** beside the DXF (best-effort, via ezdxf+matplotlib) so the sheet is viewable.
- **Design choice — semantics, not topology.** The drawing is derived from the IR's SEMANTICS, not
  from OCCT HLR: HLR's hidden edges came back *empty* and its view frame is ambiguous (measured — see
  FINDINGS). Authoring holes from what the IR *knows* is exactly what lets Ludwig draw conventioned
  detail a kernel screenshot cannot — the surface BRIEF §7 calls a wedge in its own right.
- **Grew the IR from real use (principle #7):** `toolkit.hole`/`clearance_hole` now record each hole's
  POSITION as a feature (diameter alone was kept before) — design intent the drawing engine and a
  future "move the hole" edit both need. The semantic critic (geometry-based) is unaffected.
- All conventions (sheet, scale ladder, line weights, title block, projection angle) live in
  `standards.yaml: drawing`. Wired into the compile path + webapp; gated in `--selftest` (14/14). 85 tests.
- Removed the orphaned, never-validated `drawing.compile_dxf` (it read a degenerate HLR axis — broken).

### Added — P1/S12 (Assembly type — multi-part composition)
- `toolkit.assembly(id, *children)` composes Elements into an Assembly with OCCT compound geometry
  (`GeometryService.compound`); flows unchanged through STEP, IFC (`Assembly → IfcElementAssembly`), and the
  drawing backend. `Element` gained a `children` list. 69 tests. (Per-child IFC decomposition deferred.)

### Added — P1/S11 (candidate selection)
- `loop.run(candidates=N)` generates N first-pass attempts and selects the best by the deterministic critic
  (fewest failures), then repairs the winner; `cli.py --candidates N`. With `candidates=1` behavior is
  unchanged. A pairwise *aesthetic* judge among passing candidates is deferred (needs the render backend). 68 tests.

### Added — P1/S10 (manufacturing critic — anchor cover)
- `critic/manufacturing.py`: checks each cast-in anchor's edge clearance against `standards.yaml:
  manufacturing.cover_mm` (40 mm); registered into the critic panel (adding it needed no loop change, [H4]).
- `Element` gained a `features` list; `toolkit.anchor` records each anchor's position/diameter/depth so the
  critic can reason about it. selftest 13/13, oracle 6/6, 66 tests.

### Added — P1/S9 (IFC backend — the BIM deliverable)
- `backends/ifc.py`: authors valid IFC4 via IfcOpenShell's stable low-level `create_entity` API (spatial
  hierarchy + units + an extruded-box body). The IR `type` maps to an IFC class via `standards.yaml: ifc_map`
  (`Panel → IfcWall`, `Part → IfcBuildingElementProxy`); both round-trip. The compile path emits `.ifc`
  alongside the STEP; `--selftest` round-trips it (13/13). 62 tests.
- **[H7] early-positive:** the same IR served the fab deliverable (STEP) and the BIM deliverable (IFC)
  without contortion. Fidelity note: IFC carries the semantic element + representative massing; exact
  geometry stays in the STEP (inherent to IFC). Full IFC4precast property sets deferred.

### Added — P1/S8 (Panel type + precast-panel brief)
- `toolkit.panel` (a Part of type 'Panel') + `toolkit.anchor` (a cast-in blind pocket), exposed to the live
  codegen API. Added the precast-panel brief (3000×2000×200 mm, two M16 cast-in anchors) to the frozen set,
  the reference oracle, and the codegen prompt — grown from the P1 gate, not speculatively (principle #7).
- It flows through the existing STEP + drawing backends and passes the critic. Oracle eval 6/6; 60 tests.

### Added — P0/S7 (drawing backend — HLR SVG elevation) · P0 COMPLETE
- `backends/drawing.py`: OCCT HLR → SVG elevation (via CadQuery's HLR projection) with a named-dimension
  overlay from the manifest. Best-effort and off the spine gate (HLR is fragile); falls back to a default
  projection if options are rejected. The compile path emits the SVG alongside the STEP. `--selftest` 12/12.
- **P0 spine complete (S1–S7):** prompt → exact OCCT B-rep → deterministic critic → repair → STEP
  (FreeCAD-valid) → minimal-diff `--edit` → derived drawing. First-pass 60% / post-repair 100%.

### Added — P0/S6 (--edit minimal-diff — the editability thesis)
- `agent.loop.edit` + `cli.py --edit <recipe.py> "<change>"`: re-prompt an existing program toward the
  smallest possible diff, re-verify with the critic, re-export the STEP. References are by program lineage,
  never a kernel handle ([H2]); `prompts/edit.md` enforces byte-identical untouched lines.
- Verified live: "change the holes from M8 to M10" produced a 3-line diff (the two hole calls + comment),
  0 repair rounds — a minimal edit, not a rewrite. 58 tests pass.

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
  render/present). See `BRIEF.md` (founding architecture), `docs/UX_BRIEF.md`.
- New skeleton: `ir/ geometry/ backends/ critic/ agent/ toolkit/ prompts/ store/ standards.yaml cli.py`.
- Salvaged: the provider-blind inference seam (`agent/inference.py`) and the `L_*` render toolkit
  (`backends/render_toolkit.py`, for the P1 render backend).
- Removed the mesh-substrate / wrong-shell scaffolding (the M0–M4 daemon, Next.js web, Blender adapter,
  vision-critic-as-primary). The mesh era is preserved at the git tag **`mesh-era-m4`**.

---

## Mesh era (historical — the render-tool origin; retired in the re-foundation above, preserved at tag `mesh-era-m4`)

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
