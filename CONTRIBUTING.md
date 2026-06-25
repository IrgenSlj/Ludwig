# Contributing to Ludwig

Ludwig is an **AI-native precision design compiler**: a prompt becomes a generated program that
compiles to a typed semantic IR over exact OCCT geometry, verified by a deterministic critic and
projected to derived backends (STEP/IFC/drawing/render). Read **[BRIEF.md](BRIEF.md)** (the architecture)
and **[CLAUDE.md](CLAUDE.md)** (the working conventions) before contributing.

## The gate (must stay green)

```bash
python3 cli.py --selftest     # pure-Python IR spine + a real OCCT build (kernel-guarded). No LLM tokens.
pytest -q                     # full unit suite (geometry/critic/backends skip if cadquery is absent)
ruff check                    # dead-code gate (unused imports/vars, undefined names)
python3 cli.py --eval         # first-pass geometric pass-rate on the frozen brief set (reference oracle)
```

Heavy kernels (`cadquery`, `ifcopenshell`, `bpy`) are installed per phase and **imported lazily** — never
at package import — so the skeleton and CI stay green before they are present. Keep it that way.

## Highest-leverage contributions

- **A new critic** — add a module to `critic/` exposing `name`, `applies_to`, and `evaluate(el, brief) -> Critique`
  (copy `critic/dimensional.py`), then `register` it in `critic/panel.py`. The loop must NOT change — adding a
  critic is a contained task ([H4], BRIEF §0). Deterministic checks beat eyeballing; keep the vision critic soft,
  pairwise, and render-only.
- **A new backend** — add a module to `backends/` implementing the `Backend` protocol (`name`, `fmt`,
  `fabrication`, `compile(ir, out_dir) -> Path`). Backends are *derived projections* of the IR, never authored.
- **Element-API capability** — extend `toolkit/` (the thin layer codegen registers against). Generated code
  targets **raw CadQuery** for geometry and the toolkit only to register semantics/named dims ([H1]). Don't grow
  it into a mandatory DSL, and don't add a type/op until a brief or critic finding needs it (grow from real use).
- **Standards** — domain knowledge (clearances, tolerances, line weights, IFC mappings, cover) lives in
  `standards.yaml`, not in code. Non-coders can extend it.
- **Briefs** — add to the frozen held-out set in `eval/briefs.py` to broaden the quality measurement. Never tune
  prompts/toolkit to the eval set; it is the honest signal, not a target.

## Conventions

- Python 3.11+. mm everywhere, units explicit. Measure, don't assert (back claims with an `--eval` run).
- One session/deliverable per branch/PR; keep CLI back-compat. See [docs/ROADMAP_SESSIONS.md](docs/ROADMAP_SESSIONS.md)
  for the session plan and what's next.
- Inference is bring-your-own via a CLI on `PATH` (`claude` default, `opencode` for any model). Never hard-wire a
  model or sell inference. Trusted toolkit only — no untrusted third-party skills (a tool that emits fabrication
  files cannot run untrusted code).
- `out/`, `renders/`, build caches, and `__pycache__/` are gitignored; generated artifacts don't get committed.

## License

Apache-2.0. By contributing you agree your contributions are licensed under it.
