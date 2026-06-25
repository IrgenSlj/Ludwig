"""The critic / verifier contract — the moat (BRIEF §6).

A PANEL, not one judge. Each check returns pass | fail | n/a + a message and feeds repair.
Deterministic-first: geometric/dimensional/semantic are computable; vision is demoted to soft,
pairwise, render-backend-only aesthetics. The orchestrator never knows which critics exist —
it asks for those whose `applies_to` intersects the active capabilities and aggregates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NA = "n/a"


@dataclass
class CheckResult:
    check: str            # e.g. "manifold", "dim:width", "hole_through_material"
    status: Status
    message: str = ""
    element_id: str | None = None    # which element — drives Ambient Correctness in the UI


@dataclass
class Critique:
    """The aggregate verdict the loop gates on and feeds back to repair."""
    checks: list[CheckResult] = field(default_factory=list)
    score: float | None = None       # only meaningful for ranking (pairwise) critics

    @property
    def passed(self) -> bool:
        return all(c.status is not Status.FAIL for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is Status.FAIL]

    def repair_hints(self) -> list[str]:
        return [f"{c.check}: {c.message}" for c in self.failures]


@runtime_checkable
class Critic(Protocol):
    name: str
    applies_to: set[str]             # capabilities it can judge, e.g. {"brep", "ifc", "render"}

    def evaluate(self, ir: object, brief: object) -> Critique: ...
