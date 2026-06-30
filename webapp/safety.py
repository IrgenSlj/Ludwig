"""Safety gate for the public demo — the only thing standing between a slider and remote code execution.

Ludwig compiles by `exec`-ing a Python program (design-as-code). On a developer's own machine that is
fine. Exposed publicly it is an RCE hole, and BRIEF §10 forbids running untrusted code in a tool that
emits fabrication files. So in DEMO mode a client program is allowed to execute ONLY if it is one of
the trusted gallery seeds with nothing changed but NUMBERS — i.e. only dimensions moved, no code
injected. A slider drag or a face-drag only ever rewrites numeric literals, so the full edit experience
still works; anything structural (a new call, an import, an attribute access, a changed string) is
rejected before it can run.
"""
from __future__ import annotations

import ast
import math

_MAX_PROGRAM_CHARS = 8000   # a seed + numeric edits is tiny; cap to blunt parser-DoS attempts
_MAX_ABS_DIM = 50_000.0     # mm (50 m) — every real part/element fits; blocks DoS via giant dims
                            # (a numeric-only derivative passes is_safe_derivative but huge radii blow
                            # up OCCT tessellation into millions of facets → unbounded CPU/mem/JSON).


def within_envelope(program: str, max_abs: float = _MAX_ABS_DIM) -> bool:
    """True iff every numeric literal in `program` is FINITE and |value| <= max_abs. Rejects inf/nan
    (e.g. `1e400`) and pathologically large dimensions that survive the structural gate but explode
    tessellation. Defence-in-depth alongside is_safe_derivative."""
    try:
        tree = ast.parse(program)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            v = float(node.value)
            if not math.isfinite(v) or abs(v) > max_abs:
                return False
    return True


def _normalize(program: str) -> str:
    """`ast.dump` of the program with every numeric literal flattened to 0 — so two programs that
    differ ONLY in numeric values normalize identically, while any change to a call, name, import,
    attribute, or string literal changes the dump. Positions are excluded (ast.dump default)."""
    tree = ast.parse(program)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            node.value = 0
    return ast.dump(tree)


def is_safe_derivative(program: str, seed_programs) -> bool:
    """True iff `program` is structurally identical to one of `seed_programs` except for numeric
    literal values. Conservative by construction: a new/changed call, import, attribute, name, string,
    or even a sign flip (``-25`` ↔ ``25`` change the AST shape) all fail the match and are rejected."""
    if not isinstance(program, str) or not program or len(program) > _MAX_PROGRAM_CHARS:
        return False
    try:
        norm = _normalize(program)
    except (SyntaxError, ValueError, RecursionError):
        return False
    for seed in seed_programs:
        try:
            if _normalize(seed) == norm:
                return True
        except (SyntaxError, ValueError, RecursionError):
            continue
    return False


__all__ = ["is_safe_derivative", "within_envelope"]
