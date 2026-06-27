# Ludwig — Session Roadmap

One PR per session. Every session leaves `python3 cli.py --selftest` green and the repo shippable.
This sequences [BRIEF.md](../BRIEF.md) §7 into concrete sessions. P2–P4 are deliberately held at lower
resolution — per first principle #7, grow from real use, don't pre-plan the far future.

Legend: **Gate** = the demonstrable thing that proves the session is done.

---

## S1 — Re-foundation reset (this session)
Tag `mesh-era-m4`; branch `refoundation`. Finalize the founding doc (BRIEF.md) with the 7 hardening
edits. Rewrite CLAUDE.md / README. Build the `ir/ geometry/ backends/ critic/ agent/ toolkit/ prompts/
store/` skeleton as importable stubs. Salvage the provider-blind inference (`agent/inference.py`) and the
`L_*` render toolkit (`backends/render_toolkit.py`). Delete all mesh-substrate / wrong-shell scaffolding.
**Gate:** clean tree on the new structure; skeleton imports clean; `cli.py --selftest` + CI green; BRIEF.md canonical.

## P0 — The spine

### S2 — IR core + geometry service + the pass-rate instrument
`Element/Part`, `Param` (unit-carrying), `Relation`, `NamedDim`, `ProgramNode`. `BRepHandle` + the
CadQuery/OCCT service (lazy). The thin `toolkit/` element-API seed (box, hole, register-dim).
**[H6]** Stand up the frozen held-out brief set + the `first-pass geometric pass-rate` harness in `eval/`.
**Gate:** build the bracket IR in code; bbox 80×40×6 ±1e-3, two ⌀ correct holes; pass-rate harness runs and reports a number.
**Done:** real OCCT geometry via CadQuery; `cli.py --selftest` runs the bracket gate (kernel-guarded),
`cli.py --eval` reports the pass-rate (100% on the reference oracle over a 5-brief frozen set), standards.yaml
resolves clearance holes (M8→⌀9.0). The LLM codegen builder replaces the oracle in **S3** — then the number gets real.

### S3 — The loop
Port the provider-blind inference into a real `agent/loop.py`: codegen → execute → (provisional verify) → repair,
pointed at the IR. `prompts/codegen.md` + `prompts/repair.md`. Cheap-model codegen, seam unchanged.
**Gate:** prompt → generated CadQuery program → executed IR for the bracket, end to end, headless.
**Done:** `cli.py "<prompt>"` compiles live via `claude` (bracket → exact 80×40×6 B-rep, 0 repair rounds).
`cli.py --eval --live` swaps the oracle for real codegen → **first real first-pass geometric pass-rate: 60% (3/5)**
([H1] confirmed; see `docs/FINDINGS.md`). Loop tests run token-free via mocked inference. Verify is provisional —
the real critic panel is S4.

### S4 — Deterministic critic v0
The verifier panel: `geometric` (OCCT manifold/watertight via BRepCheck), `dimensional` (named-dim exact, 1e-6),
`semantic` (units present, no orphan geometry, declared hole count). A `critic.panel` registry aggregates them;
the loop calls it and stays panel-agnostic — adding a critic is `register(...)`, not a loop change ([H4]).
**Gate:** a dimensionally-wrong bracket fails the right check; repair fixes it; re-verify passes. Loop closes on the critic.
**Done:** the panel replaced the provisional verifier without touching the loop. **Headline result:** live post-repair
geometric pass-rate **100% (5/5)** vs **60% first-pass** — the critic's exact error signal lets repair close the gap
(`cli.py --eval --live --repair`; see `docs/FINDINGS.md`). 55 tests pass.

### S5 — STEP backend + rebuilt `--selftest`
`backends/step.py` (OCCT STEP write, gated as a fabrication export per permissions). Rebuild `cli.py --selftest`
around the bracket spine (no LLM tokens). FreeCAD-open verification.
**Gate:** `cli.py "steel bracket 80×40×6, two M8 holes"` → STEP that opens in FreeCAD with correct geometry.
**Done:** `backends/step.py` exports OCCT STEP; `cli.py "<prompt>"` writes `out/<id>.py` (recipe) + `out/<id>.step`,
gated by a pre-export critic hook (no fabrication file on a failing critic). `--selftest` round-trips the STEP back
through OCCT (the kernel FreeCAD uses) and checks the bbox — 11/11. Live compile produced a valid 25 KB STEP.

### S6 — `--edit` minimal-diff + lineage/provenance
`--edit` re-prompts the program and emits a *minimal* diff. `provenance` resolves a selection to a program node
(**[H2]** never a kernel handle). Lineage stable across regeneration.
**Gate:** "make the holes M10" changes only the relevant lines; the rest of the diff is empty.
**Done:** `agent.loop.edit` + `cli.py --edit <recipe.py> "<change>"` re-prompt the program text (lineage, not a
kernel handle [H2]), print a unified diff, re-verify, and re-export the STEP. Live: "M8 → M10" produced a
3-line diff (the two hole calls + their comment), 0 repair rounds — a minimal edit, not a rewrite.

### S7 — Drawing backend (P0.5, outside the spine gate)
`backends/drawing.py`: OCCT HLR → SVG, dims queried from the manifest (ezdxf DXF deferred to the P2
conventioned-drawing engine — see the Done note). Exact↔polygonal HLR toggle.
**Gate:** the bracket yields a readable dimensioned elevation. (Fragile-by-nature; intentionally not gating the spine.)
**Done:** `backends/drawing.py` exports an OCCT HLR SVG elevation with a named-dimension overlay (best-effort,
falls back to a default projection if HLR options are rejected; never blocks the compile). The compile path
emits the SVG alongside the STEP. `--selftest` checks the SVG (12/12). DXF/ezdxf and real dimension strings
(witness lines, arrows) are deferred to the P2 conventioned-drawing engine.

**→ P0 complete:** prompt → exact B-rep → critic all-pass → STEP (FreeCAD-valid) → minimal-diff edit → derived drawing.
**All seven sessions shipped.** The compiler spine is real end-to-end; first-pass 60% / post-repair 100% on the frozen set.

## P1 — Components & domain (fabrication shop tool) — ~4–6 sessions
`Assembly`, `Panel`/`Profile`. `backends/ifc.py` (IfcOpenShell, IFC4precast). `backends/render.py` wiring the
salvaged `render_toolkit.py`. Pairwise judge panel. Real min-wall. Clearances/cover from `standards.yaml`.
**[H7] decision point:** confirm the one IR serves fab + first BIM type without contortion (or fork deliberately).
**Gate (BRIEF §7):** precast panel → IFC4precast + STEP + shop drawing + render, all critic-verified.

- **S8 — Panel type + precast brief (done).** `toolkit.panel` (type 'Panel') + `anchor` (cast-in blind pocket);
  added the precast-panel brief (3000×2000×200, two M16 cast-in anchors) to the frozen set + reference oracle +
  the live codegen API. It flows through the existing STEP + drawing backends and passes the critic. Oracle
  eval 6/6, selftest 12/12. (Render needs a Blender binary — deferred; the headless beachhead work continues.)
- **S9 — IFC backend (done).** `backends/ifc.py` authors valid IFC4 via IfcOpenShell's stable low-level
  `create_entity` API; the IR `type` maps to an IFC class via `standards.yaml: ifc_map`. The precast panel
  exports `Panel → IfcWall`, the bracket `Part → IfcBuildingElementProxy`; both re-open. The compile path
  emits `.ifc` alongside the STEP. selftest 13/13. **[H7] early-positive:** the one IR served fab (STEP) and
  BIM (IFC) without contortion. (Fidelity note: IFC carries the semantic element + a representative massing
  solid; exact holes/pockets stay in the STEP — inherent to IFC. Full IFC4precast property sets: later.)
- **S10 — manufacturing critic: anchor cover (done).** `critic/manufacturing.py` checks each cast-in
  anchor's edge clearance ≥ `standards.yaml: manufacturing.cover_mm` (40 mm), registered into the panel.
  `Element` gained a `features` list (anchors carry position/diameter/depth). selftest 13/13, 66 tests.
- **S11 — candidate selection (done).** `loop.run(candidates=N)` generates N first-pass attempts and selects
  the best by the deterministic critic (fewest failures), then repairs the winner; `cli.py --candidates N`.
  A true pairwise *aesthetic* judge among passing candidates is deferred — it needs the render backend. 68 tests.
- **S12 — Assembly type (done).** `toolkit.assembly(id, *children)` composes Elements into an Assembly with
  OCCT **compound** geometry (new `GeometryService.compound`); flows through STEP, IFC (`Assembly → IfcElementAssembly`),
  and drawing. `Element` gained a `children` list. 69 tests. (Per-child IFC decomposition deferred.)
- **Remaining P1:** `Profile` type (when a brief needs it), real min-wall analysis (research-grade), the
  **render backend** (needs a Blender binary), and IFC4precast property sets. Render is the only gate item
  blocked on the environment; everything else headless-complete.

## P2 — Buildings (architect tool) — multi-session, drawing engine alone is several
`SpatialElement`, relationship graph, `Space`/`Storey`/`Project`, hierarchical program, IDS+geometry compliance
critic, rich crystallization behavior **[H3]**, and the **conventioned drawing engine** (the real moat / hardest part).

## P3 — The application (Tauri shell, the Stage & Director UI — see docs/UX_BRIEF.md)
Desktop shell, representation switcher, point-to-navigate, ambient correctness, plan-mode/permissions/hooks,
parameter sliders, exploration contact-sheet, presentation auto-assembly backend.

## P4 — Scale
Hierarchical agentic loop over a deep IR (massing → plates → cores → units → details), cascade repair, branching.
