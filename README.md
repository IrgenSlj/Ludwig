# Ludwig

**AI-native precision design.** Describe what you want; Ludwig compiles a precise, parametric model,
verifies it is correct and fabricable, and emits drawings, fabrication files, and presentations — all
re-promptable. Named for Mies van der Rohe. *Less is more.*

> **Status:** the interaction-core rebuild (R1–R34, see [docs/REBUILD_ROADMAP.md](docs/REBUILD_ROADMAP.md))
> is complete — live direct manipulation, a deterministic fabricability critic, 2D sketch + true
> sections, op-based agent edits, and STEP/IFC/DXF/shop-drawing backends, behind a token-free public
> demo. Ludwig was previously a mesh render tool; the mesh era is preserved at the git tag `mesh-era-m4`.

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

Incumbent CAD/BIM suites keep an opaque, direct-manipulated file. You can't diff it, can't re-prompt it,
can't derive a guaranteed-correct drawing from it. Ludwig keeps the *program*, verifies geometry
deterministically, and treats every drawing and fab file as a derived view — the workflow the incumbents
structurally cannot offer.

## Architecture

See **[BRIEF.md](BRIEF.md)** for the founding architecture and first principles;
**[docs/REBUILD_ROADMAP.md](docs/REBUILD_ROADMAP.md)** for the canonical session-by-session plan
(R1–R34, supersedes the earlier `docs/ROADMAP_SESSIONS.md`);
**[docs/UX_BRIEF.md](docs/UX_BRIEF.md)** for the desktop UI/UX direction (Phase 3).

```
ir/ geometry/ backends/ critic/ agent/ toolkit/ prompts/ store/ standards.yaml cli.py webapp/
```

## Run it

```
python3 cli.py "a steel bracket, 80 x 40 x 6 mm, two M8 clearance holes"   # compile → out/<id>.{py,step,ifc,svg}
python3 cli.py --serve                                                      # web UI on http://localhost:8765
python3 cli.py --selftest                                                   # the regression gate (no LLM tokens)
python3 cli.py --eval [--live] [--repair]                                   # geometric pass-rate
```

Compiling needs the OCCT kernel (`cadquery`, `ifcopenshell`) and a `claude`-like CLI on PATH; run through
the project venv (`./run.sh` knows it). `webapp/` is the real UI ↔ engine seam (the [Stage](webapp/README.md),
sliders, per-element selection); `prototype/` is the art-directed mock, not wired to the engine.

## License

Apache-2.0 (core, local-first, forever). See [LICENSE](LICENSE) and [NOTICE](NOTICE).
