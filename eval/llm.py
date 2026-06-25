"""Live LLM codegen builder for the pass-rate harness.

Swapping `reference.build` for this is the whole point of [H6]: the harness stops reporting the
oracle's trivial 100% and starts reporting the *real* first-pass geometric pass-rate — how reliably
the model writes correct CadQuery against our thin API. FIRST-PASS ONLY (no repair), so the number is
honest about raw codegen reliability. Costs real inference tokens; gated behind `cli.py --eval --live`.
"""
from __future__ import annotations

from agent.loop import Brief, first_pass, run
from ir.elements import Element


def build(brief: dict) -> Element:
    """First-pass only (no repair) — the raw codegen-reliability measurement ([H6])."""
    _program, el, err = first_pass(Brief.from_dict(brief))
    if el is None:
        raise RuntimeError(err or "no element produced")
    return el


def build_repaired(brief: dict, *, rounds: int = 2) -> Element:
    """Post-repair: the full loop with the critic panel driving up to `rounds` repairs.
    The harness then judges the final IR — so the rate reflects what the loop actually ships."""
    res = run(Brief.from_dict(brief), rounds=rounds)
    if res.ir is None:
        raise RuntimeError(res.error or "no element produced")
    return res.ir
