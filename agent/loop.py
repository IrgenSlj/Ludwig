"""The agentic loop — the compiler driver (BRIEF §5).

    prompt → codegen → execute (build IR) → VERIFY (critic panel) →
             if fail: repair (fix only failures, keep intent) → re-verify
             if pass: select (pairwise, P1+) → compile backends

This is the skeleton shape. The pieces land across P0:
  S3 codegen+execute · S4 critic+repair · S5 STEP backend · S6 --edit minimal-diff.
The loop must stay backend/critic-agnostic — adding either must not modify this file (BRIEF §0 gate).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agent.inference import infer


@dataclass
class Brief:
    """The locked intent a candidate is generated and graded against."""
    prompt: str
    named_dims: dict[str, float] = field(default_factory=dict)   # declared dims the critic enforces
    units: str = "mm"


@dataclass
class LoopResult:
    program: str
    ir: object                       # the built IR (list[Element] / Project) — typed in P0/S2
    critique: object                 # critic.base.Critique
    passed: bool
    rounds: int


def run(brief: Brief, *, candidates: int = 1, rounds: int = 3,
        codegen_model: Optional[str] = None) -> LoopResult:
    """Generate→verify→repair until the critic passes or rounds run out.

    Wired in P0/S3–S4. Kept importable now so the skeleton and tests are honest.
    `infer(...)` is the provider-blind call (cheap tier for codegen, best tier for the critic).
    """
    raise NotImplementedError(
        "agent.loop.run — wired in P0/S3 (codegen+execute) and S4 (critic+repair). "
        "Inference seam (agent.inference.infer) is ready."
    )


__all__ = ["Brief", "LoopResult", "run", "infer"]
