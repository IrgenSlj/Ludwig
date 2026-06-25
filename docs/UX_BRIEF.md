# Ludwig — UI/UX & Art Direction Brief (P3 input)

*This is the Claude Design handoff, preserved here so the Code side builds to its seams from P0.*
*It is the input to Phase 3 (the Tauri desktop shell). It does not change the Code-side architecture —
but it hardens which IR/critic/loop seams must exist and be real by the time P3 starts.*

> North star: **Mies — "less is more."** Precision, restraint, the work as hero. A **viewfinder, not a cockpit.**

## The one tension the interface resolves
Precise parametric representation vs early-stage design ambiguity. CAD forces resolution to determinism
immediately, which is why architects abandon parametric tools at the concept stage. An LLM is the first
technology that takes ambiguity *in* and emits determinism *out*. **The interface manages the journey from
loose to locked.** It must also make dependency and breakage *ambient* (the parametric paradox), never
something the user holds in their head.

## The paradigm: "The Stage & the Director" (five surfaces)
1. **The Stage** — the design, near-fullscreen, as one continuous object. A fluid **representation control**
   moves 3D ↔ plan ↔ section ↔ elevation ↔ render. Not file tabs — one object reinterpreted, with physical
   transitions (a section plane sweeps the solid; a render develops over the geometry).
2. **The Intent Bar** — summon-able (Raycast/Spotlight-style), the *primary input*. No command ribbon; you
   describe, the agent compiles the operations.
3. **The Activity Rail** — the agent's work, separate from conversation: done / running / blocked / next.
   Interruptible, collapsible. You glance at it; you don't live in it.
4. **Point-to-Navigate Program** — click an element on the Stage → its node in a hierarchical program outline
   highlights, its parameters surface as in-place controls, the conversation turns that shaped it link.
   Geometry is the index into the program. A collapsible outline — deliberately NOT a node-graph.
5. **Ambient Correctness** — the verifier's state painted onto the design, continuously, never a dialog.
   Amber = below-spec, red = fail/clash, cool teal-green = verified & fabricable. Calm, not alarmist. The moat made visible.

## Signature interactions (the soul — prototype these)
- **Graceful crystallization** *(the signature)* — every region on a loose→locked spectrum; invent the visual
  language for "40% crystallized" and the feel of locking (graphite-sketch → hard-line).
- **Cascade made visible** — grab a parameter, dependents light up *before* you change anything; show repair.
- **Exploration as a surface** — branches are cheap (program diffs); the Stage fans into a critic-ranked
  contact-sheet of variants.
- **Parameter controls** = field + slider + cascade preview. Direct param edits are free; structural change goes through the Intent Bar.

## Art direction (tokens)
Near-monochrome canvas (warm paper-white / deep graphite). The only saturated color is (a) the design and
(b) the critic's signals (amber / red / teal-green). One restrained structural accent. Matte, hairline rules,
subtle grain — Braun-via-Rams / Teenage-Engineering honest-instrument feel. Typography does real work: a
rational humanist grotesque for UI; a true drafting mono for dims/params/program; a real drawing line-weight
hierarchy (cut / visible / hidden / dimension). Motion is meaning: representation changes are physical.
Two calm themes: paper-light, graphite-dark.

---

## Code-side seams this brief assumes (the P0→P3 contract — OWN THESE EARLY)

The UI is only possible if the compiler exposes these. Each is a Code-side obligation; the phase is when it must be real.

| UI surface | Requires from the IR / loop / critic | Phase it must be real |
|---|---|---|
| Representation switcher (3D↔plan↔section↔render) | **Real derived backends** off one IR — STEP/drawing/render are *projections*, never separate authored files | drawing P0.5 · render P1 · the rest P2 |
| Point-to-Navigate | `provenance: ProgramNode` on every element; selection → **program node**, never a kernel handle (**[H2]**) | P0 (S6) |
| In-place parameter sliders | `manifest: list[NamedDim]` + `params` are named, typed, unit-carrying; named dims feed BOTH critic and sliders | P0 (S2) |
| Ambient Correctness | The **deterministic critic** returns per-element `pass/fail/n-a` + message — real signal, not vibes | P0 (S4) → P2 compliance |
| Cascade preview / repair | The relationship graph (`relations`) + the repair loop are inspectable | graph P2 · repair P0 |
| Graceful crystallization | `crystallization: float` per element. **[H3] P0/P1 = critic-strictness scalar only**; the rich loose-geometry behavior is specified and built **P2–P3**, with this UI | scalar P0 · behavior P2–P3 |
| Exploration contact-sheet | Branches = program diffs; the loop emits **ranked** candidates (pairwise judge) | P1 |
| Activity Rail | The agentic loop surfaces todos / tool-calls / critic results as a stream, interruptible | loop P0 · surfaced P3 |
| Plan-mode / permissions / hooks | Gate fabrication export (STEP/IFC write) behind confirmation; pre-export validation hook | designed-in P0, surfaced P3 |

**The one tension to manage between the two briefs:** the UI makes crystallization *the* signature, but the
Code side must NOT bake loose-geometry representation into the IR core early (**[H3]**). Resolution: the IR
carries the `crystallization` **field** from P0 (cheap; gives Design a real seam to bind to), but its
*behavior* lands in P2–P3 alongside the UI that makes it visible. Field early, behavior with the app.
