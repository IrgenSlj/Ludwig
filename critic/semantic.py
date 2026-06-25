"""Semantic critic — holes pass through material, hosting valid, no orphan elements,
units present on every Param (BRIEF §6). Wired in P0/S4.
"""
from __future__ import annotations

from critic.base import CheckResult, Critique, Status

name = "semantic"
applies_to = {"brep", "ifc"}


def evaluate(ir: object, brief: object) -> Critique:  # noqa: ARG001
    raise NotImplementedError("semantic.evaluate — P0/S4")
