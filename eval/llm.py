"""Live LLM codegen builder for the pass-rate harness.

Swapping `reference.build` for this is the whole point of [H6]: the harness stops reporting the
oracle's trivial 100% and starts reporting the *real* first-pass geometric pass-rate — how reliably
the model writes correct CadQuery against our thin API. FIRST-PASS ONLY (no repair), so the number is
honest about raw codegen reliability. Costs real inference tokens; gated behind `cli.py --eval --live`.
"""
from __future__ import annotations

from agent.loop import Brief, first_pass
from ir.elements import Element


def build(brief: dict) -> Element:
    _program, el, err = first_pass(Brief.from_dict(brief))
    if el is None:
        raise RuntimeError(err or "no element produced")
    return el
