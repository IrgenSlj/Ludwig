"""Contract-driven loop (M4): generate → run → evaluate, engine/sensor-agnostic.

This is the minimal, *real* demonstration that the contracts compose into a working
loop — one candidate, optional repair. The production multi-candidate panel + rounds
still lives in ``ludwig.run`` (the gate). Migrating that loop onto this orchestrator is
a later, eval-verified step (BRIEF.md §5: ludwig.py "becomes core/orchestrator.py").
"""
from __future__ import annotations

from pathlib import Path

import ludwig

from . import registry
from .contracts import Sensor, ToolAdapter
from .models import Brief, Critique, RunResult


def _aggregate(critiques: list[Critique]) -> float:
    scores = [c.score for c in critiques if c.score is not None]
    return round(sum(scores) / len(scores), 2) if scores else 0.0


def run_via_contracts(
    brief: Brief,
    project_dir: str | Path,
    *,
    engine: str = "blender",
    generate=None,
) -> dict:
    """Run one candidate through the contracts and evaluate it with matching sensors."""
    adapter: ToolAdapter = registry.get_adapter(engine)
    generate = generate or ludwig.generate_scene_code

    code = generate(brief.text)
    result: RunResult = adapter.run(code, Path(project_dir))

    sensors: list[Sensor] = registry.sensors_for(adapter.capabilities())
    critiques = [s.evaluate(result, brief) for s in sensors] if result.ok else []
    return {
        "result": result,
        "critiques": critiques,
        "score": _aggregate(critiques),
        "sensors": [s.name for s in sensors],
    }
