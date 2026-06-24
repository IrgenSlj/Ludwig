# CLAUDE.md — working instructions for Ludwig

## What Ludwig is
An AI-native design tool: a prompt becomes a **generated, editable program** (the source of
truth), run through a self-correcting loop — `generate → run → evaluate → repair` — that keeps
the best result. Today the engine is **Blender** (Python `bpy`) and the evaluator is a **vision
critic**; both are designed to be swappable (CadQuery/IFC engines, geometry/schema validators).

## The plan of record
**[BRIEF.md](BRIEF.md) is the working spec.** It defines the architecture, the core contracts
(`ToolAdapter`, `Sensor`), and the milestone roadmap (M0–M6). Read it before any structural work.

## Milestone discipline (non-negotiable)
- **One milestone per branch/PR.** Implement only the current M{n} deliverable; do not start M{n+1}.
- **Strangler-fig:** wrap the working `ludwig.py`, don't rewrite it. The contracts refactor is M4 —
  until then, new code (the daemon) imports `ludwig.py` thinly.
- **The gate at every milestone:** `python3 ludwig.py --selftest` stays green (pure-Python unit
  suite + a real Blender render through the toolkit, ~2s, no LLM tokens), and the eval harness
  (`python3 ludwig.py --eval`) stays runnable. `cli/`-equivalent CLI back-compat must not break.
- After M4, a new engine/sensor must be addable **without modifying the orchestrator**. If it can't,
  the contracts are wrong — fix the contracts, not the loop.

## Key facts about the current code
- `ludwig.py` — orchestrator + loop. `run(brief, *, candidates, rounds, target, workers)` returns
  the winning `{code, critique, score, png, hero}`. `run_edit(from_path, instruction)` is the
  re-prompt path. `selftest()` is the regression guard. Importable as a module.
- `ludwig_blender_lib.py` — the `L_*` realism toolkit, prepended to every generated scene.
- `eval/` — frozen brief suite + `results.jsonl` history; the measured quality signal.
- Inference is **bring-your-own** via a CLI on `PATH` (`claude` default, `opencode` pluggable).
  **Never sell/hardcode inference** — BYO stays free forever.

## Conventions
- Python 3.11+ (dev env is 3.14). Keep the core dependency-light; the daemon may add FastAPI/SQLite.
- `renders/` and `__pycache__/` are gitignored; generated artifacts don't get committed.
- Quality is **measured, not asserted** — back claims with an eval run, not vibes (see docs/FINDINGS.md).
