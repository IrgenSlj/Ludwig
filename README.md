# Ludwig

**AI-native precision design.** Describe what you want; Ludwig compiles a precise, parametric model,
verifies it is correct and fabricable, and emits drawings, fabrication files, and presentations — all
re-promptable. Named for Mies van der Rohe. *Less is more.*

> **Status:** re-foundation in progress (P0 — the spine). Ludwig was previously a mesh render tool;
> it is now a precision CAD/BIM compiler. The mesh era is preserved at the git tag `mesh-era-m4`.

## The idea

A design is not an opaque file you push vertices into — it is a **program** that compiles to geometry.
Ludwig treats a typed semantic **IR** (intermediate representation) as the source of truth: a graph of
typed elements that own exact OpenCASCADE B-rep geometry, named dimensions, parameters, and relationships.
Everything you export — STEP, IFC, DXF/SVG drawings, renders, presentation decks — is a **derived backend**,
a projection of that IR. Edits are re-prompts against the program.

Around it runs a self-correcting loop — **generate → verify → repair** — driven by a **deterministic
critic** (manifold/watertight/dimensional/semantic checks, not eyeballing). The geometry kernel (OCCT via
CadQuery), the backends, and the critic are all swappable. Inference is **bring-your-own** via a CLI on your
`PATH` (`claude` by default; `opencode` for any model). BYO inference stays free, forever.

```
natural language + program  ──►  typed semantic IR (the truth)  ──►  STEP · IFC · DXF/SVG · render · PPTX
                                         ▲   │
                                         └── critic = verifier (generate → verify → repair)
```

## Why this, and not CAD

Incumbents (Autodesk &c.) keep an opaque, direct-manipulated file. You can't diff it, can't re-prompt it,
can't derive a guaranteed-correct drawing from it. Ludwig keeps the *program*, verifies geometry
deterministically, and treats every drawing and fab file as a derived view — the workflow the incumbents
structurally cannot offer.

## Architecture

See **[BRIEF.md](BRIEF.md)** for the founding architecture, first principles, and the P0–P4 roadmap;
**[docs/ROADMAP_SESSIONS.md](docs/ROADMAP_SESSIONS.md)** for the session-by-session plan;
**[docs/UX_BRIEF.md](docs/UX_BRIEF.md)** for the desktop UI/UX direction (Phase 3).

```
ir/ geometry/ backends/ critic/ agent/ toolkit/ prompts/ store/ standards.yaml cli.py
```

## License

Apache-2.0 (core, local-first, forever). See [LICENSE](LICENSE) and [NOTICE](NOTICE).
