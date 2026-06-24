"""Vision critic sensor (M4) — the existing 5-axis critic behind the Sensor contract.

Wraps ``ludwig.critique`` (Claude views the render) + ``ludwig._score`` /
``ludwig._axis_scores`` for parsing. No behavior change — just the contract seam, so a
``GeometryValidator`` / ``IfcValidator`` can later drop in alongside it (BRIEF.md §4).
"""
from __future__ import annotations

import re

import ludwig

from core.models import Brief, Critique, RunResult


def _parse_fixes(text: str) -> list[str]:
    """Pull the FIXES bullet list out of a critique block."""
    hints: list[str] = []
    in_fixes = False
    for line in (text or "").splitlines():
        if line.strip().upper().startswith("FIXES"):
            in_fixes = True
            continue
        if in_fixes:
            m = re.match(r"\s*[-*]\s*(.+)", line)
            if m:
                hints.append(m.group(1).strip())
            elif line.strip():
                break
    return hints


class VisionCritic:
    name = "vision"
    applies_to = {"image", "render"}

    def evaluate(self, result: RunResult, brief: Brief) -> Critique:
        png = result.primary_render
        if not png:
            return Critique(score=0.0, issues=["no render to evaluate"])
        raw = ludwig.critique(brief.text, png)
        return Critique(
            score=float(ludwig._score(raw)),
            axis_scores=ludwig._axis_scores(raw),
            repair_hints=_parse_fixes(raw),
            raw=raw,
        )
