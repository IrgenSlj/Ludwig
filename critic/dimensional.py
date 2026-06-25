"""Dimensional critic — every named dim in the brief is present and EXACT (BRIEF §6).

The low-noise heart of the moat: this is the signal the mesh-era vision critic never had
(see docs/FINDINGS.md). Tolerance from standards.yaml (`tolerances.linear`, default 1e-6).
Wired in P0/S4.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Status

name = "dimensional"
applies_to = {"brep"}


def evaluate(ir: object, brief: object) -> Critique:  # noqa: ARG001
    raise NotImplementedError("dimensional.evaluate — P0/S4")
