"""Geometric critic (OCCT) — manifold, watertight, no self-intersection, min-wall (BRIEF §6).

min-wall is a P0 heuristic and NEVER a P0 gate (OCCT booleans throw StdFail_NotDone exactly
there; real analysis is P1). Wired in P0/S4.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Status

name = "geometric"
applies_to = {"brep"}


def evaluate(ir: object, brief: object) -> Critique:  # noqa: ARG001
    raise NotImplementedError("geometric.evaluate — P0/S4")
