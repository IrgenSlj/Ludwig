<!-- Generated 2026-06-29 by a parallel spec workflow: 8 architect agents (one per
workstream) speccing against the real code, then a synthesis pass. Canonical schedule
for the interaction-core rebuild. Each R# is one PR; cli.py --selftest stays green. -->

# Ludwig Rebuild Roadmap — Interaction Core

Rebuild the interaction model; keep the verified spine (IR, OCCT kernel, deterministic critic, STEP/IFC/drawing backends, the loop). Replace LLM-exec'd CadQuery as the only geometry path with a deterministic params->geometry compiler, direct manipulation, reviewable structured Ops, and live 2D/sections.

## Rules (every session, no exceptions)
- One session = one PR.
- `python3 cli.py --selftest` stays green (pure-Python spine green before kernel; cadquery branch when present). Token-free.
- Each session has a demonstrable gate. CLI back-compat never breaks.
- Additive-first: new types default off/None; fallbacks preserved so no capability regresses.
- [H1] DAG/ops are recorded side-effects of existing toolkit calls, never a mandatory authoring DSL — codegen keeps writing raw CadQuery + thin side-car.
- [H2] program text stays canonical; references are program lineage, never kernel handles.

## Phase shape
- **P1 Truth + No-Compile Core** — see real OCCT B-rep in Studio; stand up the deterministic params->geometry evaluator. De-risks the whole thesis.
- **P2 Instant Direct Manipulation** — wire the evaluator into preview; drag geometry handles -> named dims, no LLM in the path.
- **P3 Op-Based Agent Edits + Typed AEC** — agent edits via validated invertible Ops; Stair/Wall/Opening typed elements + AD-K compliance critic.
- **P4 Streaming Agent Runtime** — non-blocking SSE footer lane with reviewable Plan/Build chips, consuming the Op schema.
- **P5 2D Sketch + True Sections** — constraint-solved sketches -> extrude; void-aware poché cut sections; live in Studio.

---

## Phase 1 — Truth + No-Compile Core

**R1 — Real B-rep in the Studio viewport (kill the stand-in stair)** [STUDIO-WIRING]
Port buildSolid/showGeometry from index.html into studio.html's dual-camera frame()/setCam; boot via POST /api/adopt with a vendored bracket seed; honest empty-stage on null mesh; window.LUDWIG.render/state seam.
Gate: --selftest green; with server+kernel up /studio shows the adopted bracket (orbit/fit/iso/ortho); token-free window.LUDWIG.render(_assemble dict) draws a solid + badge.
Depends: —

**R2 — FeatureNode/FeatureGraph types + toolkit recorder (no eval)** [DAG-EVAL]
New pure-Python ir/feature.py; additive Element.graph=None; contextvar recorder in toolkit/elements.py (box/hole/anchor/place/stack/assembly append typed nodes), default OFF, zero behavior change.
Gate: pure-Python --selftest builds bracket under recorder -> box#1 + hole#1 + hole#2 with correct inputs/params and lineage-stable ids reproducible across runs; existing tests green.
Depends: —

**R3 — Deterministic params->geometry evaluator (full re-eval, parity)** [DAG-EVAL]
New geometry/evaluator.py: evaluate(graph)->BRepHandle dispatching each op to the locked GeometryService primitives. No caching — prove the NO-LLM compiler matches the closures.
Gate: cadquery branch — for every graph-expressible frozen brief, evaluator bbox / cylindrical_face_count / is_valid equals the eval/reference.py oracle within bbox_gate.
Depends: R2

**R4 — Content-hash cache + incremental set_param (tree-reduction)** [DAG-EVAL]
EvalCache + per-node content key (op + resolved unit-carrying params + input keys, floats rounded to tol); evaluator.set_param recomputes only dirty descendants, returns rebuilt set.
Gate: editing one param rebuilds EXACTLY the dirty set (bracket length -> box+both holes; assembly top resize -> top+compound, NOT base); rebuilt-count == dirty-set size.
Depends: R3

**R5 — Studio model tree + Properties + critic verdict from real IR** [STUDIO-WIRING]
Replace hardcoded left-rail tree with payload-derived tree; right-rail sliders generated from payload.dims (editable extents) -> /api/preview on drag, /api/edit on release; real deterministic critic verdict from payload.critic (kill fake AD-K).
Gate: --selftest green; injected _assemble payload lists real element id + dims, one slider per editable extent, verdict reflects real critic; slider release round-trips /api/edit when kernel present.
Depends: R1

**R6 — Studio pick-selection + Ambient Correctness + CLI rewire** [STUDIO-WIRING]
Raycaster pick on #view (movement-threshold so drag stays orbit) -> elementId -> program node; tree<->stage highlight; per-child critic colour wash; footer runCommand viewport cmds kept, param/free-text rerouted to /api/edit instruction.
Gate: --selftest green; multi-child payload: selectFromStage highlights+isolates, tree click pulses solid, failing critic paints amber/red.
Depends: R5

---

## Phase 2 — Instant Direct Manipulation

**R7 — Wire the evaluator into preview_edit (instant manipulation)** [DAG-EVAL]
webapp/service.preview_edit uses recorded graph + evaluator.set_param when a graph is available (graph cached per program text), else falls back to _substitute_all_literals; identical /api/preview contract; now drives non-extent params (hole diameter). agent/loop.execute opts into recording without breaking the closure path.
Gate: tests/test_webapp.py — bracket slider drag goes through evaluator, only dirty subtree rebuilt, contract unchanged; webapp+loop tests green; visibly instant in studio.
Depends: R4, R5

**R8 — Node->span write-back for minimal-diff durable edit (optional)** [DAG-EVAL]
Record source_span per node (AST of executed <ludwig-program>); durable edit substitutes the NODE's literal by span, removing the ambiguous-literal LLM fallback.
Gate: edit_to_result / --edit yields a minimal one-token diff for a 30x30 square's length with NO LLM call (today falls to LLM — literal not unique).
Depends: R7

**R9 — Dim binding metadata in the result JSON (the bridge)** [BIDIRECTIONAL]
Extend _dims() to tag each NamedDim with axis (0/1/2 via shared _EXTENT_AXIS, else null) and editable; surfaced through compile/preview/_variant_payload. Purely additive.
Gate: --selftest green; test asserts length/width/height carry axis 0/1/2 + editable, diameter editable axis null, hole dims flagged non-axis; no slider-path behavior change.
Depends: R6

**R10 — Face-drag write-back (output-directed extents) — the marquee** [BIDIRECTIONAL]
On face pick: world normal -> nearest ±axis -> extent dim (R9 metadata); on-geometry drag arrow streams /api/preview (camera fixed, refit:false); release commits via /api/edit.
Gate: pick bracket top face, drag up -> height rises live, zero LLM, zero file writes; release writes STEP at new height, diff +1/-1.
Depends: R9, R7

**R11 — Span-identity binding — kill value-collision LLM fallbacks** [BIDIRECTIONAL]
New webapp/bind.py (ast+tokenize) maps dim-name -> exact literal span(s) incl. `L=80; box(id,L,...)`; thread optional span into preview_edit/_try_fast_edit; bbox-axis re-measure still gates acceptance (wrong span rejected, never written).
Gate: --selftest covers bind on bracket + a 30x30 square; test shows square `length` editing on the deterministic fast path with inference.infer asserted-not-called.
Depends: R10, R8

**R12 — Selection-driven prompting (lineage-scoped agent edits)** [BIDIRECTIONAL]
Selected element/face/dim scopes footer instruction to that element id ("On element '<id>': ...") + attaches selected dim as the param fast-path. Lineage-based ([H2]), works on assembly children.
Gate: select assembly child `top`, "make it 20 mm taller" -> only top changes; test asserts scoped instruction/param reaches agent.loop.edit.
Depends: R11

**R13 — Hole-position drag — the honest boundary** [BIDIRECTIONAL]
Drag hole in plan: preview re-bores by span-substituting position literals (R11) + re-measuring cylindrical centroid; no bbox signature so COMMIT routes through /api/edit (LLM) with a scoped instruction — documented binding boundary.
Gate: drag previews re-bored solid live; release -> minimal +1/-1 diff, new centre confirmed by cylindrical-face re-measure; non-deterministic commit flagged in FINDINGS.
Depends: R12

---

## Phase 3 — Op-Based Agent Edits + Typed AEC

**R14 — Op vocabulary + deterministic text-patch apply/invert** [OP-API]
New agent/ops.py: frozen Op dataclasses (AddElement, AddFeature, RemoveFeature, SetParam, Place, Assemble) each -> toolkit primitive, to_source()/apply()->(new_text, inverse_op); Plan.apply_to. Hoist _substitute_* / _comment_regions out of webapp/service into ops; service imports them. Op-spine check in selftest pure-Python section. tests/test_ops.py.
Gate: --selftest green WITHOUT cadquery: 3-op bracket plan rendered onto empty program is byte-identical to the GOOD bracket recipe; apply-then-inverse returns original; existing ambiguity test passes post-hoist.
Depends: R11

**R15 — Build path: render Plan -> execute -> verify -> assemble** [OP-API]
webapp/service.build_to_result(program, plan): render plan, run existing execute()+verify()+_assemble() (fab gate untouched); return standard result + difflib diff + inverse Plan.
Gate: kernel-gated — build_to_result('', bracket_plan)['passed'] True, artifacts include step+ifc, diff added==3; STEP withheld when critic not all-pass.
Depends: R14

**R16 — Planner: LLM emits validated JSON ops (data, never exec'd)** [OP-API]
New prompts/plan.md; ops.parse_plan strict-validates (unknown kind/param -> raise, never exec) + JSON extractor; agent/loop.plan(instruction,*,program,brief,model)->Plan via one inference.infer() on the best tier.
Gate: mocked-inference test — JSON bracket plan -> parse -> apply -> execute -> verify passes; unknown op kind rejected, nothing exec'd.
Depends: R15

**R17 — Propose -> review -> apply in loop + cli --plan/--apply, invertible undo** [OP-API]
loop.propose() returns Plan with per-op summaries; apply() builds + returns inverse Plan; loop.edit() retained as fallback. cli --plan <recipe> "<instr>" (prints ops) and --apply (builds, writes minimal diff, exports STEP on all-pass), routed before positional/--edit.
Gate: --plan prints 1-op plan; --apply yields +1-line diff + passing critic; mocked review/apply/undo test; positional + --edit unchanged.
Depends: R16

**R18 — Webapp /api/plan + /api/build; studio Plan/Build wiring** [OP-API]
server.py /api/plan (propose, writes nothing) + /api/build (apply reviewed plan, returns result + inverse), mirroring explore/adopt. service.plan_to_result/build_to_result. Wire studio Plan/Build pill + agent lane stub to the two endpoints.
Gate: token-free — hand-written bracket plan to build_to_result re-executes, passes critic, writes artifacts; /api/plan returns ops without writing.
Depends: R17, R6

**R19 — Stair type + deterministic geometry compiler** [AEC-ELEMENTS]
geometry/service.prism(profile_xz, width, plane) extruding a closed polyline (no booleans); toolkit.stair(...) builds saw-tooth flight as one prism, type='Stair', registers rise/going/width/floor_to_floor/riser_count + features; Stair->IfcStair in standards.yaml maps.
Gate: --selftest builds Stair, bbox = run×width×ftf within gate, is_valid true, cylindrical_face_count==0; pure-Python spine green when cadquery absent.
Depends: R4

**R20 — AD-K compliance critic, registered with no loop change** [AEC-ELEMENTS]
standards.yaml stairs: block (private/general/institutional use-classes + 2R+G band); critic/compliance.py (NA for non-Stair) reads use_class from brief + rise/going/width from el.dim, emits rise/going/pitch/2R+G CheckResults; appended to critic/panel _PANEL; use_class added to Brief.from_dict. loop body unchanged.
Gate: --selftest evaluates one compliant + one over-pitch stair via panel.evaluate -> PASS then FAIL deterministically; pre-existing critiques unaffected (NA for Parts/Panels).
Depends: R19

**R21 — Stair brief + oracle in the frozen eval set** [AEC-ELEMENTS]
eval/briefs.py stair brief (dims length=run/width/height=ftf, holes:0, use_class, stair params); eval/reference.py stair branch via toolkit.stair; numbers chosen private-compliant / general-non-compliant.
Gate: harness.run(reference.build) stays 1.0 with stair included; stair survives bbox/hole/validity.
Depends: R20

**R22 — Wall + Opening typed elements** [AEC-ELEMENTS]
geometry/service.cut(handle, box_spec) (generic rect boolean); toolkit.wall(...) type='Wall', toolkit.opening(...) type='Opening' cutting the void + Relation('hosts', opening.id); Opening->IfcOpeningElement in maps.
Gate: --selftest builds Wall hosting one Opening: wall is_valid, void reduces volume / adds void face, hosts Relation present; existing briefs unaffected.
Depends: R19

---

## Phase 4 — Streaming Agent Runtime

**R23 — Headless streaming agent-runtime + token-free SSE endpoint** [AGENT-RUNTIME]
agent/runtime.py: plan_stream(instruction, state,*,infer,apply,should_cancel,on_event) generator yielding {op|applied|done|error|cancelled}, infer/apply INJECTABLE (default = deterministic local grammar->set_param, zero tokens). service.agent_stream(...) reuses _variant_payload shape. server.py _agent_stream() GET /api/agent_stream copying _compile_stream SSE framing.
Gate: --selftest pure-Python check — plan_stream('going 320', state) yields a set_param op then 'done', deterministic + token-free; back-compat unchanged.
Depends: R6

**R24 — Footer lane wired: EventSource consumer + Plan/Build chips** [AGENT-RUNTIME]
studio runCommand() stub -> EventSource('/api/agent_stream?...') ported from index.html compile(); each 'op' renders Accept/Reject chip; #agentmode pill gates: Plan = wait for Accept, Build = auto-accept.
Gate: manual — 'going 320' in Build rebuilds via a real op chip; in Plan the chip waits, applies only on Accept; selftest green (R23 contract test).
Depends: R23

**R25 — Non-blocking + interruptible (Stop)** [AGENT-RUNTIME]
Footer Stop closes EventSource; plan_stream honors should_cancel() and stops, emitting 'cancelled'; killable Popen inference variant or between-ops cancel check; running indicator prevents double-submit; viewport stays navigable (client-side three.js).
Gate: --selftest — plan_stream(should_cancel=lambda:True) emits zero ops + 'cancelled'; manual — Stop mid-plan halts new chips while viewport keeps navigating.
Depends: R24

**R26 — Real LLM op-planner behind the seam (consumes Op schema)** [AGENT-RUNTIME]
prompts/plan.md -> JSON array of OP-API ops; injected infer calls inference.infer at cheap tier (loop._tier_model('codegen')); ops parsed+validated against OP-API schema, malformed dropped with error chip (never exec'd); Accept routes to OP-API.apply against program lineage; reuses service critic/mesh serialization.
Gate: --selftest injects fake infer returning canned JSON, asserts N valid ops parsed + malformed rejected, token-free; live LLM path manual.
Depends: R25, R17

---

## Phase 5 — 2D Sketch + True Sections

> Section overlap resolved: SECTIONS owns the canonical `GeometryService.section` primitive (R29); 2D-SKETCH's section view (R31) consumes it rather than adding a second cut path.

**R27 — Sketch IR + constraint solver seam (pure-Python)** [2D-SKETCH]
ir/sketch.py (Point2D/Line/Circle/Arc + Constraint set), zero heavy deps; geometry/sketch_solver.py SketchSolver protocol + NumericSolver (scipy.least_squares when present, pure-Python Gauss-Newton fallback) returning coords + DoF report; sketch distance/radius dims register as NamedDim. planegcs (LGPL) documented as the industrial upgrade behind the seam (no GPL SolveSpace in-process).
Gate: --selftest pure-Python — 4-line rectangle (coincident+H/V+two distance dims) solves to exact corners within tol 1e-6; under-constrained variant reports correct remaining DoF; green before kernel.
Depends: —

**R28 — Sketch -> extrude: the deterministic params->geometry compiler** [2D-SKETCH]
service.extrude(profile_wire, depth) + face_from_wire via polyline().close().extrude() -> lazy BRepHandle (errors surface via execute()); toolkit sketch/line/rect/circle/constraint + extrude(sketch,depth)->Element registering dims; codegen API list updated; L/T-profile brief added to eval.
Gate: --selftest builds L-profile from constrained sketch (bbox + section area correct, STEP round-trips); --eval oracle stays 100% with +1 brief.
Depends: R27

**R29 — Section op + void-aware cut profile** [SECTIONS]
service.section(handle,*,axis,offset,keep)->kept solid (oversized half-space box intersection, isolating StdFail_NotDone) + section_profile(...) returning {outer, inners} (u,v) loops via FRONT/RIGHT/TOP mapping; sections each solid of a compound. No drawing code.
Gate: --selftest cadquery block cuts bracket at YZ: kept bbox ~40×40×6, one profile loop area ~240 mm² at x=0, inner (hole) loop appears at x=25; pure-Python spine green when absent.
Depends: —

**R30 — Section drawing backend: poché + beyond** [SECTIONS]
backends/section.py self-registering (import in backends/__init__; no loop change) emitting <id>_section.dxf + best-effort PNG; hatches poché on a CUT layer (wires unused standards line_weights_mm.cut + new poché key), heavy cut boundary, thin beyond silhouette via _straight_edges, true-mm dims via DIMLFAC, reusing shopdrawing _View/_uv helpers; 'section' label added to cli _LABELS + webapp map.
Gate: --selftest — bracket section DXF readable, >=1 HATCH on POCHE/CUT layer, CUT layer present, dims recover true mm; compile path lists the artifact.
Depends: R29

**R31 — Section / plan as a derived sketch view** [2D-SKETCH]
Draw the true cut profile of the sketched non-prismatic solid with poché through the existing _uv/_View model, reusing R29's section primitive; closes the 'true section for non-prismatic solids' gap. Best-effort/isolated.
Gate: --selftest cuts the L-profile at mid-height, recovers expected closed section polyline (vertex count/area within tol), drawn into DXF/SVG; existing drawing checks green.
Depends: R28, R29

**R32 — Sketch DoF critic into the deterministic panel** [2D-SKETCH]
critic/sketch.py: under-constrained -> WARNING with remaining DoF, conflicting/redundant/unsolved -> ERROR; registered via critic.panel.register ([H4]); result carries element_id+severity for the Ambient wash.
Gate: --selftest — over-constrained sketch fails with the right message, fully-constrained passes; panel gained a critic with no agent/loop.py change.
Depends: R28

**R33 — A re-promptable, live cut plane** [SECTIONS]
toolkit.section(el,*,axis,offset,name) records {kind:'section',...} on el.features (grow-the-IR pattern); service.section_to_result(program, plane) runs section + tessellate(kept) returning a section mesh; studio data-tool='section' drives a live cut, no LLM/compile in the geometry path. Default = centroidal longitudinal plane.
Gate: --selftest builds a brief with a declared section, backend cuts on that exact plane; token-free webapp payload returns a non-empty section mesh for the bracket.
Depends: R30, R6

**R34 — Studio 2D representation: live sketch edit + instant section** [2D-SKETCH]
service.solve_sketch/section path mirroring preview_edit (re-solve + section in-process, NO files/LLM); numeric-extent fast-path extended so a sketch distance dim drag re-solves; studio stub 2D tools (line/rect/circle/dim/constrain/section) wired to the real sketch; 2D shows constrained sketch, 3D shows live extrude, Section slices live. Token-free via window.LUDWIG.render.
Gate: /studio loads L-profile sketch, drag a sketch dimension -> sketch re-solves and both extruded 3D and derived section update instantly, no compile/LLM call.
Depends: R31, R32, R33, R6

---

## Cross-cutting notes / scope boundaries
- **Coverage bound**: raw-CadQuery-closure briefs (filtered_bracket, slotted_plate, chamfered_spacer, counterbored_plate) are NOT graph-expressible — evaluator/incremental path needs a `raw` escape-hatch node and the text-substitution fallback stays for everything else.
- **Structural-edit lineage [H2]**: op-counter ids are stable under PARAM edits only; insert/remove re-records via program re-exec, never mutates the graph. Incremental path is scoped to param edits.
- **Deterministic verifiability is bbox-axis-only**: extent-face drags are fully deterministic; hole position / fillet / angle / chamfer have no acceptance test and commit via LLM (stated, not hidden).
- **Trust boundary**: parse_plan rejects unknown kinds/params and never exec's — the safety win over today's exec'd CadQuery.
- **Incremental critic is out of scope** for P1–P2: preview still re-runs the full critic panel each tick; only geometry is made incremental. Flag as a separate workstream.
- **Studio gates**: studio.html is not exercised by --selftest, so every Studio session pairs 'selftest green' with a concrete token-free window.LUDWIG.render injection gate (SSE blocks the screenshot tool — use POST /api/adopt).
