# CLAUDE.md — working instructions for Ludwig

## What Ludwig is
**AI-native precision design.** You describe what you want; Ludwig **compiles** a precise,
parametric model — a typed semantic IR owning exact OCCT B-rep geometry — verifies it is correct
and fabricable with a **deterministic critic**, and emits the derived backends (STEP/IFC for fab+BIM,
DXF/SVG drawings, render, presentation). The model is a **re-promptable program**, never an opaque
file. The loop is `generate → verify → repair`. Engine, backends, and critic are all swappable.

> Ludwig is a **compiler**: natural language + a hierarchical program → the IR (the truth) →
> derived backends. CadQuery/OCCT is the geometry *service*; IFC/STEP are *backends*; neither is
> the truth. See **[BRIEF.md](BRIEF.md)** — the founding architecture & roadmap. Read it first, every session.

## The plan of record
**[BRIEF.md](BRIEF.md)** is the spec (architecture, first principles, P0–P4). **[docs/ROADMAP_SESSIONS.md](docs/ROADMAP_SESSIONS.md)**
sequences the work session-by-session. **[docs/UX_BRIEF.md](docs/UX_BRIEF.md)** is the P3 UI/UX seam.

## Phase discipline (non-negotiable)
- **One session deliverable per branch/PR.** Implement only the current session's slice; do not skip ahead.
- **The gate at every phase:** `python3 cli.py --selftest` stays green (pure-Python checks; later, a real
  OCCT build through the toolkit), and the eval harness (`first-pass geometric pass-rate` over a frozen
  held-out brief set) stays runnable. CLI back-compat must not break.
- After the contracts exist, a new **backend** or **critic** must be addable **without modifying the loop**.
  If it can't, the contracts are wrong — fix the contracts, not the loop.
- **Grow the IR from real use.** Add a type or op only when a brief/critic finding demands it. Never pre-build the ontology.

## Locked conventions (from BRIEF §10 — do not relitigate without sign-off)
- **mm everywhere, units explicit and asserted.** The #1 silent CAD bug.
- **Codegen targets raw CadQuery + a thin element-API side-car** that registers named dims into the
  manifest. **Measure raw-vs-wrapped first-pass geometric pass-rate before expanding the wrapper.**
  Do NOT mandate "element-API only" — it trades away reliability we can't spare (~50% first-pass).
- **`--edit` must produce a minimal diff.** A rewrite-on-edit is a bug; editability is the whole thesis.
- **References are by program lineage, never persistent kernel handle.** Topological naming is the CAD rewrite trap.
- **Domain semantics live in `standards.yaml`** (e.g. M8 clearance hole = ⌀9.0). Codegen consults it.
- **Deterministic-first critic.** Vision is demoted to soft, pairwise, aesthetic-only, render-backend-only.
- **Provider-blind, local-first, BYO inference** via the thin CLI seam (`agent/inference.py`). Never sell inference.
  Cheap model for bulk codegen; best model reserved for the critic / hard reasoning.
- **Trusted toolkit only.** No untrusted third-party skills/plugins (a tool that emits fabrication files
  cannot execute untrusted code).
- **Measure, don't assert.** Back claims with a pass-rate run, not vibes (`docs/FINDINGS.md`).

## Key facts about the current code (P0 skeleton — being filled in)
- `ir/` — the typed element model (`Element`, `Param`, `Relation`, `NamedDim`, `ProgramNode`, crystallization).
- `geometry/` — the OCCT/CadQuery service + `BRepHandle` (heavy deps imported lazily).
- `backends/` — derived projections; `render_toolkit.py` is the salvaged `L_*` Blender toolkit (P1 render backend).
- `critic/` — the deterministic verifier panel.
- `agent/` — `inference.py` (the provider-blind seam, salvaged) + `loop.py` (generate→verify→repair).
- `toolkit/` — the thin element-API codegen registers against.
- `cli.py` — entry + `--selftest`. `standards.yaml` — the project-standards file.

## Conventions
- Python 3.11+ (dev env is 3.14). Core stays dependency-light; heavy kernels (cadquery, ifcopenshell, bpy)
  are imported lazily inside the modules that need them, never at package import time (keeps `--selftest`/CI green
  before they're installed).
- `renders/`, build artifacts, and `__pycache__/` are gitignored; generated artifacts don't get committed.
- **The recoverable history of the mesh era is the git tag `mesh-era-m4`.** Anything deleted in the
  re-foundation is one `git checkout mesh-era-m4 -- <path>` away.
