"""The critic panel — the registry + aggregator the loop asks (BRIEF §6, the moat).

The orchestrator never knows which critics exist: it calls `evaluate`, which runs every registered
critic whose `applies_to` intersects the active engine capabilities and aggregates one `Critique`.
Adding a new critic/Sensor is `register(...)` — it must NOT require touching the loop (BRIEF §0 gate / [H4]).
"""
from __future__ import annotations

from critic import compliance, dimensional, geometric, manufacturing, semantic, sketch
from critic.base import Critique

# Default panel for the Blender/CadQuery brep world. New sensors append here via register().
_PANEL: list = [geometric, dimensional, semantic, manufacturing, compliance, sketch]


def register(critic) -> None:
    """Add a critic (anything exposing name/applies_to/evaluate) without modifying the loop."""
    _PANEL.append(critic)


def critics() -> list:
    return list(_PANEL)


def evaluate(ir, brief, *, capabilities=frozenset({"brep"})) -> Critique:
    caps = set(capabilities)
    checks = []
    for c in _PANEL:
        if set(c.applies_to) & caps:
            checks.extend(c.evaluate(ir, brief).checks)
    return Critique(checks=checks)
