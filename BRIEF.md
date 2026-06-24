# Ludwig — Development Brief & Morph Plan

**From:** a single-CLI Python script that turns a prompt into a Blender render via a generate→render→critique loop.
**To:** a daemon-centric, BYO-agent, open-core platform that turns a prompt into an *editable, re-promptable* 2D/3D model for designers and architects — starting in product/3D-viz, built to expand into AEC and engineering.

This document is written to be handed to Claude Code (or any coding agent) as the working spec. Drive it milestone by milestone, one PR per milestone, with `--selftest` and the eval harness staying green as the gate.

---

## 1. Vision in one paragraph

A design is not a dead file you push vertices into — it is a **prompt plus a generated, editable program**. Ludwig keeps the program as the source of truth (diffable, re-generatable, steerable by language) and wraps it in a self-correcting loop: generate candidate programs, run them through a creative engine, *evaluate the result*, repair, keep the best. The loop is the moat; the engine and the evaluator are both pluggable. Today the engine is Blender and the evaluator is vision; tomorrow the engine is CadQuery or IfcOpenShell and the evaluator is a geometry or IFC-schema validator. The product runs **local-first with bring-your-own inference**, with an optional hosted layer for the things only a server can do.

## 2. First principles (carry these into every decision)

1. **The loop is the product; the sensor is swappable.** "Claude views its own render" is the *first* sensor, not the moat. The moat is `generate → run → evaluate → repair`. Design every interface so a new evaluator (watertightness check, IFC validation, clash detection) drops in without touching the loop.
2. **Design-as-code is the source of truth.** Never persist an opaque artifact as the primary record. Persist the program that produced it. Edits are re-prompts against that program.
3. **The daemon is the only privileged process.** A web frontend talks to a local daemon; the daemon owns the filesystem, the secrets, the engine subprocesses, and the agent spawn. This is what lets the same codebase be both "local-first" and "deployable web app."
4. **Don't ship an agent — adapt to whichever one is on `PATH`.** One stdio adapter per CLI, swappable. BYO-inference stays free forever; never sell inference.
5. **Skills are code; standards are files.** The `L_*` toolkit stays Python. But units, tolerances, drawing conventions, IFC property sets, and material libraries are **markdown files** the agent reads at generation time, so a non-coder can extend them.
6. **Lock the brief before the model draws (RULE 1).** Every fresh request begins with a discovery question-form, not output. For CAD this is non-negotiable: guessing units, scale, or tolerance is catastrophic, not cosmetic.
7. **Substrate determines market — expand deliberately.** Blender/mesh = product-viz, ships today. AEC (IFC) and engineering (STEP) need a *second engine*, not more `L_*` functions. They are milestones, not checkboxes.

## 3. Target architecture

```
┌──────────────────────── Browser (Next.js) ─────────────────────────┐
│  chat · discovery form · 3D viewer (glTF) · file workspace ·        │
│  candidate gallery · version diff · settings/BYOK                   │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │ /api/* (SSE for streaming)
                                 ▼
┌──────────────── Local daemon (Python · FastAPI · SQLite) ───────────┐
│  agent registry      ← PATH scan + one adapter per CLI               │
│  skill + standards loader  ← reads markdown/SKILL.md from disk       │
│  prompt assembler    ← composes the prompt stack                    │
│  ORCHESTRATOR        ← the generate→run→evaluate→repair loop         │
│  engine manager      ← spawns + pools engine subprocesses           │
│  project/artifact store ← SQLite + on-disk project folders          │
└───────────┬───────────────────────────────────────┬─────────────────┘
            │ spawn(agent_cli)                       │ spawn(engine)
            ▼                                        ▼
   claude · opencode · codex · …          Blender (headless) · [CadQuery] ·
   write programs in the engine's          [IfcOpenShell] — execute the
   language, calling its toolkit           program, emit artifacts
            │                                        │
            └──────────────► Artifacts ◄─────────────┘
        scene program (.py/.step/.ifc) · render (.png) · preview (.glb) · logs
```

**Key stack decision — keep the daemon in Python.** open-design is Node because its engine is the browser. Ours is not: Blender's `bpy`, IfcOpenShell, CadQuery, and build123d are **all Python**. A Python daemon (FastAPI + `better-sqlite`-equivalent, e.g. plain `sqlite3`/SQLModel) means the orchestrator, the engines, and the toolkits share one runtime and one language. This is a real advantage over the open-design pattern, not a copy of it. The web frontend stays Next.js/React (Vercel-deployable later); the daemon stays Python.

| Layer | Stack |
|---|---|
| Frontend | Next.js (App Router) + React + TypeScript; SSE for live progress |
| Daemon | Python 3.11+ · FastAPI · SQLite (SQLModel or `sqlite3`) · SSE streaming |
| Agent transport | `subprocess` over stdio; one parser per CLI protocol |
| Engine transport | `subprocess` (headless Blender today); in-process for pure-Python engines (CadQuery) later |
| Preview | Engine exports `.glb`; web renders via `<model-viewer>` or three.js |
| Storage | On-disk `projects/<id>/` (programs + outputs) + SQLite (projects, runs, messages, artifacts) |
| Inference | BYO CLI on `PATH`; OpenAI-compatible BYOK proxy as fallback |

## 4. Core contracts (the highest-value engineering)

Define these as Python `Protocol`s in `core/contracts.py`. Everything else plugs into them.

**ToolAdapter — one per creative engine (engine-agnostic).**
```python
class ToolAdapter(Protocol):
    name: str                       # "blender", "cadquery", "ifc"
    language: str                   # the language the agent writes in
    def capabilities(self) -> Caps  # {mesh, brep, ifc, 2d}, output formats
    def toolkit_reference(self) -> str   # the L_* / helper docs injected into the prompt
    def run(self, program: str, project_dir: Path) -> RunResult
        # executes the agent-written program; returns render(s), .glb preview,
        # exported model (.step/.ifc), stdout/stderr, structured errors
    def preview(self, result: RunResult) -> Path   # path to web-viewable .glb
```

**Critic / Sensor — one per evaluation modality (loop-agnostic).**
```python
class Sensor(Protocol):
    name: str
    applies_to: set[str]            # which capabilities it can judge
    def evaluate(self, result: RunResult, brief: Brief) -> Critique
        # Critique = { score, axis_scores, issues[], repair_hints[] }
```
- `VisionCritic` (today): renders → agent views → 5-axis score. The existing critic, moved behind this interface.
- `GeometryValidator` (later): manifold/watertight, bounding-box vs declared dimensions.
- `IfcValidator` (later): schema validity, required property sets, simple clash.

The orchestrator never knows which sensors exist — it asks the registry for sensors whose `applies_to` intersects the active engine's capabilities, runs them, and aggregates.

**Skill — a folder, not a plugin.** `SKILL.md` + `assets/` + `references/`. Frontmatter: `mode`, `engine`, `scenario`, `outputs`, `requires_standards`, `example_prompt`. Loaded pre-flight and injected into the prompt.

**Standards — portable markdown.** `standards/units.md`, `standards/tolerances.md`, `standards/drawing-conventions.md`, `standards/ifc-property-sets.md`, `materials/*.md`. The active set is injected into the prompt stack. Non-coders edit these.

**Discovery form — a JSON schema emitted before generation.** For a modeling brief: units, overall dimensions/scale, tolerance class, target output (render / print / manufacture / drawing / BIM), style or reference, hard constraints. The cost of a wrong direction becomes one form, not one finished model.

**Prompt stack — composable, every layer a file:**
```
discovery directives (RULE 1 form, repair directives)
  + identity + critic charter
  + active standards (units, tolerances, materials)
  + active SKILL.md (+ injected toolkit reference)
  + project metadata (units, target output, candidate history)
  + adapter toolkit reference (L_* docs)
```

## 5. Current → target component map

| Today (Ludwig as-is) | Becomes | Action |
|---|---|---|
| `ludwig.py` orchestrator/loop | `core/orchestrator.py` | **Reuse** the loop logic; wrap behind the daemon API |
| `ludwig_blender_lib.py` (`L_*`) | `adapters/engines/blender/toolkit.py` | **Reuse** as the Blender adapter's toolkit |
| provider switch (`claude`/`opencode`) | `adapters/agents/*` registry | **Generalize** to a PATH scan + per-CLI adapter |
| critic / 5-axis scoring | `sensors/vision_critic.py` | **Refactor** behind the `Sensor` interface |
| eval harness (`--eval`, `--selftest`) | `eval/` | **Keep**; wire into CI and the daemon's quality gate |
| CLI entry (`ludwig.py "..."`) | `cli/ludwig.py` | **Thin wrapper** calling `core` — back-compat preserved |
| — | `daemon/` (FastAPI + SQLite) | **New** |
| — | `web/` (Next.js) | **New** |
| — | 3D viewer + `.glb` export | **New** (see §6) |
| — | discovery form engine | **New** |
| — | skill + standards loaders | **New** |

## 6. The preview layer (where the open-design analogy breaks)

open-design's artifact is HTML that renders instantly in an iframe — the browser *is* the engine. Ludwig's artifact is a 3D scene that must be rendered by Blender and then shown in the browser. Two distinct surfaces:

1. **Hero render (raster).** The Cycles `.png` you already produce. Shown as the candidate image. No change.
2. **Interactive preview (geometry).** The Blender adapter additionally exports a **`.glb`** of the winning (and ideally each) candidate. The web renders it with `<model-viewer>` (simplest) or three.js (more control) — orbit, turntable, relight. This is what makes "look at it from another angle / it's a real object, not a picture" true, and it's the thing image-gen cannot do.

`.glb` is the universal interchange that keeps this engine-agnostic: when CadQuery/IfcOpenShell arrive later, they export to `.glb` for preview too (via their own tessellation), while *also* emitting the precision format (`.step`/`.ifc`) as the real deliverable.

## 7. Phased roadmap (solo-developer paced — sizes, not promises)

Order is load-bearing. Each milestone leaves the repo shippable and the eval green. **Strangler-fig principle: wrap the working `ludwig.py`, don't rewrite it.**

- **M0 — Daemon skeleton (S).** FastAPI app with one endpoint that runs the *existing* loop via a thin import of current `ludwig.py`. SQLite project/run store. CLI still works unchanged. *Deliverable: `POST /api/generate` returns the same result the CLI does, persisted.*
- **M1 — Web shell (M).** Next.js chat + live progress (SSE: todo/candidate/score stream) + file workspace listing the project folder. Drives M0. *Deliverable: type a prompt in the browser, watch candidates and scores stream, see the hero render.*
- **M2 — Interactive 3D preview (M).** Blender adapter exports `.glb` per candidate; web viewer with orbit/turntable. *Deliverable: rotate the generated object in the browser.* This is the differentiator made visible.
- **M3 — Discovery form / RULE 1 (M).** Mandatory pre-generation question-form with the CAD constraint schema (units, scale, tolerance, target output). Locks the brief; feeds the prompt stack. *Deliverable: no generation starts before the brief is locked.*
- **M4 — Contracts refactor (L).** Extract `ToolAdapter` and `Sensor` protocols. Move Blender behind `ToolAdapter`, the vision critic behind `Sensor`. Stand up the skill + standards file loaders and the composable prompt stack. *Deliverable: the architecture in §3–§4 is real; adding an engine or sensor is now a contained task.*
- **M5 — BYO-agent registry (L).** PATH scan + per-CLI adapters (start: `claude`, `opencode`, `codex`) swappable from the UI; OpenAI-compatible BYOK proxy fallback with SSRF blocking. *Deliverable: pick your agent in a dropdown.*
- **M6 — First precision vertical (XL — gate behind all the above).** Pick **one**: (a) add a `GeometryValidator` sensor (watertight/manifold + dimension check) to prove the sensor-pluggability claim end-to-end, or (b) add a second `ToolAdapter` — **CadQuery → STEP** (mechanical) or **IfcOpenShell → IFC** (architecture, your moat). Time-box the research; this is the leap from viz to CAD.

## 8. Open-core & monetization line

- **Apache-2.0 core (free, local-first, forever):** daemon, orchestrator/loop, all adapters and sensors, the `L_*` toolkit, the viewer, skills, standards. BYO-inference.
- **Hosted layer (later, separate, paid):** managed **render farm** (Cycles is slow — real, recurring value), team **collaboration + versioning**, curated **asset & standards libraries**, SSO/governance for firms. *Do not sell inference — it contradicts the BYO core.*

## 9. Scope discipline — explicit non-goals for v1

- No 2D dimensioned drafting / constraint solver (it's an Onshape-grade moat; defer).
- No multi-engine on day one — Blender only until M6.
- No real-time multiplayer / collaboration (that's the hosted upsell, not the core).
- No cloud/hosted service until the local product is loved.
- No marketplace, no plugin store.

## 10. Proposed repo structure

```
ludwig/
  core/
    orchestrator.py      # the loop (from ludwig.py)
    contracts.py         # ToolAdapter, Sensor protocols
    prompt_stack.py
    models.py            # Brief, RunResult, Critique, Project
  adapters/
    engines/
      blender/{adapter.py, toolkit.py}   # toolkit = ex ludwig_blender_lib
      cadquery/           # M6 (optional)
    agents/{claude.py, opencode.py, codex.py, base.py}
  sensors/
    vision_critic.py
    geometry_validator.py # M6 (optional)
  skills/<skill>/SKILL.md
  standards/{units.md, tolerances.md, drawing-conventions.md, ...}
  materials/*.md
  daemon/{app.py, db.py, sse.py, routes/}
  web/                    # Next.js
  eval/                   # existing harness
  cli/ludwig.py           # thin back-compat wrapper → core
```

## 11. How to drive this with Claude Code

1. Commit this file as `BRIEF.md` at the repo root; reference it from `CLAUDE.md`.
2. Work **one milestone per branch/PR**. Open each session with: *"Read BRIEF.md. We are on M{n}. Implement only M{n}'s deliverable. Keep `--selftest` and the eval harness green. Do not start M{n+1}."*
3. Keep `cli/ludwig.py` passing its existing selftest at every milestone — it's your regression guard while the daemon grows around it.
4. After M4, when adding any engine or sensor, the prompt is: *"Implement a new `{ToolAdapter|Sensor}` per `core/contracts.py`; do not modify the orchestrator."* If that constraint can't be met, the contracts are wrong — fix them, not the loop.

## 12. Risks & mitigations

- **Scope creep** → strangler-fig (M0 wraps, doesn't rewrite); one engine, one sensor until M6.
- **Blender process management** (startup cost, concurrency, crashes) → an engine manager that pools/recycles headless Blender processes; treat each run as isolated and disposable.
- **glTF fidelity** for preview → preview is for *inspection*, not the deliverable; keep the raster hero render as the quality artifact.
- **The viz→CAD leap (M6)** is genuinely research-grade → time-box it; treat a working `GeometryValidator` as the cheaper proof before committing to a second kernel.
- **Solo bandwidth** → milestones are independently shippable; the repo is portfolio-grade at every step, which serves the career goal regardless of whether it becomes a business.
