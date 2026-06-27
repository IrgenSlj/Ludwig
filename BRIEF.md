# LUDWIG — Founding Architecture & Build Roadmap

*Handoff document for Claude Code. Read this first, every session. It fixes the decisions that are expensive to reverse and sequences the whole build.*

> **Ludwig** — AI-native precision design. Describe it; Ludwig compiles a precise, parametric model, verifies it is correct and fabricable, and emits drawings, fabrication files, and presentations — all re-promptable.

---

## 0. What changed, and why this document exists

Ludwig began as a mesh render tool (Blender + a vision critic). It is now an **AI-native precision CAD/BIM system** targeting fabrication-grade geometry, true vector drawings, and presentation output — the workflow the incumbent CAD/BIM suites structurally cannot offer, because their files are opaque and direct-manipulated, while ours is a re-promptable program.

The mesh kernel is the wrong substrate for precision and fabrication (triangles approximate; they have no exact circle, fillet, or analytic surface, and you cannot derive a dimensionally-exact drawing or a fabrication file from them). We swap the substrate and the critic; we keep the harness (the generate→verify→repair loop and provider-blind inference).

This is a multi-session build. Do not treat any single phase as the product.

### 0.1 Hardening edits over the first draft (what a CTO review changed, and why)

These seven changes were folded in after a sourced due-diligence pass. They do not alter the spine, the phasing, or the thesis; they harden the three places the first draft was writing checks the research says would bounce. Each is marked **[H#]** where it appears.

1. **[H1] Codegen target = raw CadQuery + a thin semantic side-car — measured, not assumed.** First-pass *geometric* correctness of LLM-written CadQuery is only ~50% (Query2CAD 53.6%; CAD-Coder IoU ~0.52), and the 90%+ numbers in the literature are all *fine-tuned* models, not a stock CLI call. Custom DSLs measurably raise hallucination/syntax-error rates. The original "generated code calls the element API only, never raw CadQuery" pre-committed the answer to the very experiment §8 says to run. Reversed: see §5, §10.
2. **[H2] References are by program lineage, never persistent kernel handle.** Topological naming (stable refs to faces/edges across regeneration) is the classic CAD rewrite trap — unsolved even in Onshape/Parasolid (PLDI'23). New first principle #8.
3. **[H3] Crystallization is a critic-strictness scalar through P1.** No loose-geometry *representation* in the IR core until P2+, when its behavior is actually specified. See §3.
4. **[H4] The moat is the loop, not the IR.** IR-first is the dominant CAD paradigm (IFC, the parametric feature tree, OCCT's own XDE/XCAF) — table stakes, not a differentiator. The defensible edge is the *productized* verifier-driven loop + swappable contracts + BYO inference. (CADSmith, 2025, is essentially this architecture in paper form — validation, and a ship-before-it-commoditizes signal.) See §1.
5. **[H5] The Anthropic Agent SDK is one adapter behind the thin-CLI seam, not the orchestration foundation.** The SDK is Claude-shaped; "provider-blind via the SDK" means a LiteLLM-style proxy and degraded tool-use on non-Claude models. The existing thin-CLI seam is *less* locked-in. See §4, §5.
6. **[H6] One tracked number from day one: first-pass geometric pass-rate on a frozen held-out brief set.** It predicts product viability better than anything else and operationalizes "measure, don't assert." See §8, §10.
7. **[H7] "One engine serves both beachheads" is a hypothesis to validate by P1, not a locked principle.** See §1, §7.

---

## 1. The thesis in one frame: **Ludwig is a compiler**

```
   SOURCE LANGUAGE                 IR (the truth)                 BACKENDS (derived)
 ┌───────────────────┐        ┌──────────────────────┐        ┌────────────────────┐
 │ natural language  │        │  typed semantic      │   ───► │ STEP / IGES  (fab) │
 │   +               │  ───►  │  element model        │   ───► │ IFC          (BIM) │
 │ hierarchical      │        │  (a graph of typed   │   ───► │ DXF / SVG  (drawing)│
 │ program           │        │   elements owning    │   ───► │ glTF / Blender (rndr)│
 └───────────────────┘        │   exact B-rep geom)   │   ───► │ PDF / PPTX  (present)│
          ▲                   └──────────┬───────────┘        └────────────────────┘
          │                              │
          │                        ┌─────▼──────┐
          └──── repair ◄─────────── │  CRITIC =  │  deterministic geometric/semantic
                                    │  VERIFIER  │  + compliance + (vision, demoted)
                                    └─────┬──────┘
                                          │
                            generate → verify → repair  (the agentic loop = compiler driver)
```

The **first-class citizen is the IR** — a typed semantic element model — *not* a geometry library (CadQuery) and *not* an export format (IFC). CadQuery/OCCT is the geometry **service** the IR calls; IFC is one **backend** the IR compiles to. Confusing either of those for the truth is the mistake that forces a rewrite later.

**[H4] The IR-first architecture is correct but it is not the moat.** It is the dominant paradigm — IFC enforces exactly this semantic/geometry split; the parametric feature tree has been the persistent record since Sketchpad/Pro-E; OCCT ships it as XDE/XCAF. Everyone serious is IR-first. **The defensible edge is the productized self-correcting loop, the swappable contracts (engine ↔ backend ↔ critic), and BYO inference.** Build and message accordingly.

**[H7] Under this frame, "components-up vs building-down" is a *scheduling* question** (which element types and which backends we implement first), *hypothesised* to be a single engine serving both beachheads. A bracket, a precast panel, and a building are all IR trees; they differ in depth and in which types are populated. **This is a hypothesis to validate by the end of P1, not a locked principle** — fab (exact STEP B-rep, tight tolerance) and BIM (IFC semantics, deliberately-Low-LoD geometry, spatial/compliance) have genuinely different critics and fidelity regimes. Prove the spine on ONE beachhead before letting BIM types touch the core IR.

---

## 2. First principles (LOCKED — do not relitigate without explicit sign-off)

1. **Design-as-code.** The source of truth is a program, never an opaque file. Every change is a diff. Editability is the entire competitive reason to exist.
2. **IR is the first-class citizen.** A typed semantic element model. Geometry, params, type, and relationships live on elements.
3. **OCCT is the geometry service.** Exact B-rep via **CadQuery** (default; larger codegen corpus → more reliable generation) over OpenCASCADE. The wrapper is swappable (build123d is the alternative); the *kernel* (OCCT) is locked.
4. **Backends are derived, never authored.** STEP, IFC, DXF/SVG, render, PPTX are all projections of the IR.
5. **Deterministic-first critic.** Most of "brief adherence" is *computable*, not eyeballed. The vision critic is demoted to soft aesthetic judgments on the render backend only. (This is why precision CAD is a *better* regime for the agentic loop than rendering was — the error signal becomes exact.)
6. **Local-first, BYO-model, provider-blind.** Keep the existing pluggable inference (thin CLI-on-PATH seam). Trusted toolkit only — **no untrusted third-party skills/plugins** (a tool that emits fabrication files cannot execute untrusted code; cf. 2026 agent-skill supply-chain attacks).
7. **Grow the IR from real use, never speculatively.** Start the type hierarchy minimal; let the critic's findings tell you the next type/op to add.
8. **[H2] References are by lineage in the regenerated program, never by persistent kernel handle.** Topological naming breaks even in Onshape/Parasolid; the program is the only stable identity. `provenance` and point-to-navigate resolve a selection to a *program node*, never to a raw OCCT face/edge ID.

---

## 3. The IR — the typed semantic element model

Start minimal. This is the seed, not the finished ontology.

```python
class Element:
    id: str
    type: str                 # "Part", "Wall", "Space", ...
    name: str
    geometry: BRepHandle      # lazy OCCT solid built by the program
    params: dict[str, Param]  # named, typed, UNIT-CARRYING values
    relations: list[Relation] # hosts / bounded_by / contains / references
    manifest: list[NamedDim]  # named dims → feed BOTH the critic and the UI sliders
    crystallization: float    # 0.0 loose ... 1.0 locked (see [H3] below)
    provenance: ProgramNode   # link back to the program node that authored it
                              # (powers point-to-navigate; resolves to a NODE, not a kernel handle [H2])
```

**Type hierarchy (grows by phase — DO NOT pre-build):**

```
Element
├─ Part              (P0)  generic precise solid
│   ├─ Panel         (P1)  precast concrete  → IFC4precast
│   └─ Profile       (P1)  joinery / extrusion
├─ Assembly          (P1)  composes Elements, preserves relative transforms
├─ SpatialElement    (P2)
│   ├─ Wall · Slab · Column · Beam · Roof
├─ Space             (P2)  program/area-bearing (the thing a brief is graded against)
├─ Storey            (P2)
└─ Project           (P2)  root
```

**Two design commitments worth stating explicitly:**

- **[H3] Crystallization is a property of every element — but through P1 it is *only* a critic-strictness scalar.** A region can be loose (indicative) or locked (precise, fabrication-final). P0/P1 ship it as a float that gates how strict the critic is on that element and nothing else — it must NOT introduce a second geometry representation into the IR core. The rich behavior (the agent holding several interpretations; loose-geometry rendering) is specified and built in P2–P3, alongside the UI that makes it visible. Do not let the seductive part metastasize into the kernel early.
- **The program is hierarchical, not flat.** "One editable program" does NOT survive at building scale. A `Project` program calls `Storey` programs call `Unit` programs call detail programs. The editability thesis holds **at each node of the tree**. How the agentic loop decomposes over this tree is the single biggest open research question (see §8).

---

## 4. The stack (mostly Python — one language end to end)

| Layer | Tech | Phase |
|---|---|---|
| Geometry kernel | OpenCASCADE via **CadQuery** | P0 |
| BIM I/O | **IfcOpenShell** | P1–P2 |
| 2D vector drawings | OCCT **HLR** → **ezdxf** (DXF) + SVG; dims queried from model | P0.5 (parts) → P2 (conventioned) |
| 3D render | **Blender headless (bpy)** as backend; reuse the salvaged `L_*` toolkit (`backends/render_toolkit.py`) | P1 |
| Live viewport | three.js / pythreejs (GL, fast) | P3 |
| Agent orchestration | **thin CLI-on-PATH seam** (provider-blind); Anthropic Agent SDK is **one adapter behind it [H5]**, not the foundation | P0 |
| Critic / verifier | OCCT checks + IDS/IFC rules + vision (demoted) | P0 → P2 |
| Presentation assembly | SVG/HTML → PDF/PPTX, composing derived views | P3 |
| App shell | **Tauri** over the Python backend; local-first, BYO Blender + model | P3 |
| Persistence | local **SQLite** (metadata, history) + git-diffable recipe files | P0 |
| Export / fab | STEP, IGES, STL, IFC, DXF, PDF, PPTX, glTF | per backend |

**[H5] Inference seam.** The boundary is the existing thin CLI adapter (`claude`/`opencode` on PATH; `agent/inference.py`). This is *less* locked-in than adopting the Agent SDK as the loop, because the SDK's system prompts/tool schemas/loop are tuned for Claude and degrade on non-Anthropic models behind a proxy. If/when we want the SDK's machinery (subagents, hooks, plan mode), it goes behind the seam as one provider adapter — never replacing it.

---

## 5. The agentic loop (the compiler driver)

Reuse the existing orchestrator shape; point it at the IR.

```
prompt ─► codegen (LLM writes a program against CadQuery + the thin element-API; see [H1])
       ─► execute (build the IR)
       ─► VERIFY (deterministic critic panel over the IR)
       ─► if fail: feed critic JSON back ─► repair (fix ONLY failures, keep intent) ─► re-verify
       ─► if pass: select (pairwise judge among candidates, P1+) ─► compile backends
```

**[H1] Codegen target.** Generated programs target **raw CadQuery with a thin semantic registration side-car** — the program writes ordinary CadQuery (the model's strongest prior) and *registers* which solids are which `Element`s and which values are named dims (`toolkit/`). The thin element-API expands only where P0 measurement proves it does not cost first-pass geometric pass-rate. We do NOT force "element-API only"; that trades away the reliability we cannot spare at ~50% first-pass.

Borrow wholesale from Claude Code (these become **app-layer** features, surfaced in P3, but design the headless core so they slot in):

- **Plan mode** — investigate → propose plan → human approves → execute.
- **Tiered autonomy / permissions** — auto-apply cheap geometry edits; **always gate fabrication export (STEP/IFC write) and destructive ops** behind explicit confirmation. Prefer reversible actions.
- **Project-standards file** (`standards.yaml`, the CLAUDE.md analogue) — units, tolerances, line weights, layer conventions, hole-clearance tables, min-wall thresholds, IFC mappings, code requirements. The single highest-leverage file.
- **Subagents** — geometry, drawing, render, compliance/critic, presentation; split-and-merge for variants.
- **Hooks** — a **pre-export validation hook** runs the deterministic critic before any fabrication file leaves the building. Last line of defense.
- **Model tiering** — cheap model for bulk candidate codegen, strongest model reserved for the critic / hard reasoning. (Note: tiering + prompt-caching economics hold on the Claude path; they largely evaporate behind a non-Anthropic proxy.)

---

## 6. The critic / verifier (the moat)

A **panel**, not one judge. Each check returns `pass | fail | n/a` + message, and feeds repair.

- **Geometric** (OCCT): manifold, watertight, no self-intersection, min-wall (approx heuristic P0 → real analysis P1; **never a P0 gate** — min-wall is exactly where OCCT booleans throw `StdFail_NotDone`).
- **Dimensional**: every named dim in the brief is present and exact (tol 1e-6). Low-noise — this is the point.
- **Semantic**: holes pass through material; hosting valid; no orphan elements; units present.
- **Compliance** (P2): IDS data-validation (ratified v1.0) **plus a geometry/rule engine** — IDS explicitly excludes geometry, computed values, and clashes, so it is necessary but not sufficient.
- **Aesthetic** (vision, DEMOTED): proportion/composition only, **pairwise** (lower variance than absolute scoring), render-backend only, soft. Never adjudicates "good architecture" — see §8.

The old vision critic was noise-limited (per-brief swings > the deltas we chased; see `docs/FINDINGS.md`). Moving the bulk of brief-adherence to deterministic checks is the core upgrade; **adopt pairwise for everything that remains a ranking.**

---

## 7. Phased roadmap

Each phase ships something usable to **one** beachhead while extending the **same** IR. Session-level breakdown lives in `docs/ROADMAP_SESSIONS.md`. One PR per session.

### P0 — The spine
Build: `Element`/`Part`, program-as-source, generate→verify→repair, **STEP** + (P0.5) **HLR→SVG** backends, CLI, `--selftest`, `--edit` (minimal-diff), and **[H6] the first-pass-geometric-pass-rate instrument** over a frozen held-out brief set.
Test fixture: a steel bracket (`80×40×6mm, two M8 holes`). The bracket is **not the goal** — it's the smallest honest proof the spine closes.
**Gate:** prompt → exact-dim B-rep (bbox ±1e-3, holes correct) → critic all-pass → STEP opens in FreeCAD → `--edit` produces a minimal diff. (The HLR→SVG elevation is P0.5, deliberately *outside* the spine gate — OCCT HLR is fragile and must not block proving the solid spine.)

### P1 — Components & domain (→ a fabrication shop has a real tool)
Build: `Assembly`, `Panel`/`Profile` types, **IFC** (IfcOpenShell) + **render** (Blender; wire in `backends/render_toolkit.py`) backends, judge panel + pairwise critic, real min-wall, hole-clearance from `standards.yaml`. **Validate [H7] here:** does the one IR genuinely serve fab + first BIM type without contortion?
**Gate:** "a precast wall panel, 3000×2000×200, two M16 cast-in anchors, 40mm cover" → IFC4precast + STEP + shop drawing + render, all critic-verified.

### P2 — Buildings (→ an architect does)
Build: `SpatialElement` types, the **relationship graph**, `Space`/`Storey`/`Project`, the **hierarchical program**, the **compliance critic** (IDS + geometry), the rich **crystallization behavior [H3]**, and the **conventioned drawing engine** (poché on cut elements, door swings, fixtures-as-symbols, dimension strings, room tags, scale-aware representation — NOT free HLR; ~41% of BIM→practice drawing work is manual, IFC barely carries annotation. This is the least-solved, highest-moat surface and may be a wedge in its own right).
**Gate:** "a 4-storey housing block, 18 units, double-height entrance" → massing → plan/section/elevation (conventioned) → area schedule (computed) → compliance pass/fail.

### P3 — The application (→ no CLI)
Build: the **Tauri desktop shell** and the **Stage & Director UI** (see `docs/UX_BRIEF.md`), parameter sliders, point-to-navigate, ambient correctness, plan-mode + permissions + hooks surfaced, **presentation auto-assembly** backend.
**Gate:** a full design produced, edited, verified, and exported without touching a terminal.

### P4 — Scale
Build: the **hierarchical agentic loop** over a deep IR (subagent decomposition: massing → plates → cores → units → details), **cascade repair**, exploration/branching at scale.
**Gate:** a real building, re-promptable at any node of the tree, without regenerating the whole.

---

## 8. Open research questions (flagged per phase — do not pretend these are solved)

- **P0:** **[H1/H6]** codegen reliability against raw CadQuery vs the thin element-API — *instrument this first*; it is the central bet of the IR layer, and `first-pass geometric pass-rate` is the number that decides the product. OCCT `StdFail_NotDone` on fillet/boolean is the dominant, opaque failure mode the repair loop must parse.
- **P1:** true manufacturability / minimum-thickness analysis; IR↔IFC fidelity (export = result geometry, not the recipe; Design Transfer View is one-way) and which MVD.
- **P2:** the conventioned-drawing problem (IFC→readable drawing is a known, unsolved pain); **the architectural critic's taste boundary — it must verify compliance and program and REFUSE to score aesthetics**, because a tool that grades "good architecture" is either wrong or smuggling an ideology.
- **P2/P4:** **[H2]** hierarchical decomposition of the agentic loop over a deep IR, and lineage-stable referencing across regeneration — the biggest unknowns in the project.
- **P3:** round-tripping direct manipulation back into clean program text (select-geometry→code is solved; writing a freehand edit back as *good* code is not); cascade visualization at building scale.

---

## 9. Repo / module structure (seed — see the live tree)

```
ludwig/
  ir/                 # Element, Param, Relation, NamedDim, ProgramNode, crystallization
  geometry/           # CadQuery/OCCT service + BRepHandle (lazy)
  backends/
    step.py  drawing.py  ifc.py  render.py  render_toolkit.py(salvaged L_*)  present.py
  critic/             # geometric.py dimensional.py semantic.py compliance.py aesthetic.py (pairwise judge)
  agent/              # inference.py (provider-blind seam), loop.py, subagents, plan-mode, permissions, hooks
  toolkit/            # the thin element-API ops codegen registers against (the new L_*)
  standards.yaml      # the project-standards file (units, line weights, clearances, min-wall, IFC map)
  prompts/            # codegen.md, repair.md, critic.md
  store/              # sqlite + recipe files
  eval/               # held-out brief set + the pass-rate harness [H6]
  cli.py
  tests/
```

## 10. Conventions Claude Code MUST follow (the `standards.yaml` / CLAUDE.md seed)

- **mm everywhere, units explicit and asserted.** The #1 silent CAD bug.
- **[H1] Generated code targets raw CadQuery + the thin element-API side-car; it registers every named dim into the manifest.** The raw-vs-wrapped first-pass geometric pass-rate is *measured* on a held-out set in P0 before the wrapper is expanded. We do NOT mandate "element-API only."
- **`--edit` must produce a minimal diff.** If an edit rewrites the file, that's a bug — editability is the whole thesis.
- **[H2] References are by program lineage, never persistent kernel handle.**
- **Domain semantics live in `standards.yaml`** (e.g. "M8 clearance hole" = ⌀9.0, not ⌀8.0). Codegen consults it.
- **Trusted toolkit only.** No untrusted third-party skills.
- **Provider-blind.** No hard-wiring to one model; cheap model for candidate codegen, best model reserved for the critic/hard reasoning.
- **[H6] Measure, don't assert.** Track `first-pass geometric pass-rate` on a frozen held-out brief set every phase. Conclusions under the noise floor need averaging/pairwise. Don't tune on the test set.
