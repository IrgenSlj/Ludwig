"""Op vocabulary — reviewable, invertible structured edits (BRIEF §5; the Op-API, R14).

An **Op is data, not code**. The planner (R16) will emit Ops as JSON; we validate and render them to
toolkit source — the model never hands us Python to `exec()`. That is the security win over exec'ing
model-authored CadQuery: a plan is inspectable and can be rejected before anything runs. Each Op writes
its own source (`to_source`); a `SetParam` also knows how to `apply` to an existing program, returning
the new text AND its inverse, so every parameter edit is undoable. A `Plan` is an ordered list of Ops:
`render()` writes the ADD ops to a fresh program; `apply_to()` threads the SetParam ops through an
existing one and hands back the inverse plan.

This module also OWNS the deterministic text-substitution primitives (hoisted out of webapp/service so
the editing spine sits below the web layer): comment-aware literal substitution, plus the targeted
constraint-value and hole-position substitutions the sketch/hole edits use. Pure-Python, no kernel.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# --------------------------------------------------------------------------- #
# substitution primitives (the deterministic editing spine)
# --------------------------------------------------------------------------- #

_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")  # a standalone number literal (not M6, not 1.5e3)


def _comment_regions(program: str) -> list[tuple[int, int]]:
    """Char ranges that are `#` comments, so a literal echoed in a comment (e.g. the codegen's own
    `# 80 (length) × 40 …`) doesn't defeat the uniqueness check."""
    regions, off = [], 0
    for line in program.splitlines(keepends=True):
        h = line.find("#")
        if h != -1:
            regions.append((off + h, off + len(line)))
        off += len(line)
    return regions


def _substitute_unique_literal(program: str, old: float, new: float) -> Optional[str]:
    """Replace the program's literal `old` with `new` — but ONLY if `old` occurs exactly once as a
    number in CODE (comments excluded). Ambiguous (0 or >1 matches, e.g. a 30×30 square) → None, so
    the caller falls back to the LLM edit. Preserves int/float spelling so the diff is one token."""
    comments = _comment_regions(program)
    in_comment = lambda pos: any(a <= pos < b for a, b in comments)  # noqa: E731
    spans = [m for m in _NUM.finditer(program)
             if abs(float(m.group()) - old) < 1e-9 and not in_comment(m.start())]
    if len(spans) != 1:
        return None
    m = spans[0]
    txt = str(float(new)) if "." in m.group() else str(int(new))
    return program[:m.start()] + txt + program[m.end():]


def _substitute_all_literals(program: str, old: float, new: float) -> Optional[str]:
    """Replace EVERY standalone code occurrence of `old` with `new` (comments excluded).

    Unlike `_substitute_unique_literal`, this handles the common case where one physical extent is
    echoed — `box(..., 120, ...)` AND `register_dim("plate_length", 120)` — which must move together.
    The caller guards against a coincidental same-valued literal by re-measuring the intended axis
    after the rebuild. Returns None if `old` never occurs in code. Preserves int/float spelling."""
    comments = _comment_regions(program)
    in_comment = lambda pos: any(a <= pos < b for a, b in comments)  # noqa: E731
    spans = [m for m in _NUM.finditer(program)
             if abs(float(m.group()) - old) < 1e-9 and not in_comment(m.start())]
    if not spans:
        return None
    out = program
    for m in reversed(spans):  # right-to-left so earlier spans' offsets stay valid
        txt = str(float(new)) if "." in m.group() else str(int(new))
        out = out[:m.start()] + txt + out[m.end():]
    return out


# a specific sketch constraint's value: constrain("distance", "L0", value=80) — targets ONLY that
# literal, never the point seed coords that share the number (R34).
_CONSTRAINT_VALUE = (
    r'(constrain\(\s*["\']{kind}["\']\s*,\s*["\']{ref}["\']\s*,\s*value\s*=\s*)(-?\d+(?:\.\d+)?)')


def _substitute_constraint_value(program: str, kind: str, ref: str, old: float, new: float) -> Optional[str]:
    """Replace the value of one sketch constraint (distance/radius on a given line/circle id), leaving
    every other literal — including the point seed coords that happen to share the number — untouched."""
    pat = re.compile(_CONSTRAINT_VALUE.format(kind=re.escape(kind), ref=re.escape(ref)))
    hits = [m for m in pat.finditer(program) if abs(float(m.group(2)) - old) <= 1e-6]
    if len(hits) != 1:
        return None                                         # 0 → not found; >1 → ambiguous, bail safely
    m = hits[0]
    return program[:m.start(2)] + f"{new:g}" + program[m.end(2):]


# a hole/anchor position tuple: clearance_hole(el, "M8", (-25, 0)) — the (x, y) literal pair (R13).
_POS_TUPLE = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)')


def _substitute_hole_pos(program: str, old_xy, new_xy) -> Optional[str]:
    """Replace one hole's position literal `(ox, oy)` with `(nx, ny)`, leaving every other literal
    untouched. Matches by the exact old coordinates, so with distinct hole positions it is unambiguous
    (0 or >1 matches → None, and the caller keeps the last good geometry)."""
    ox, oy = float(old_xy[0]), float(old_xy[1])
    hits = [m for m in _POS_TUPLE.finditer(program)
            if abs(float(m.group(1)) - ox) <= 1e-6 and abs(float(m.group(2)) - oy) <= 1e-6]
    if len(hits) != 1:
        return None
    m = hits[0]
    return program[:m.start()] + f"({float(new_xy[0]):g}, {float(new_xy[1]):g})" + program[m.end():]


# --------------------------------------------------------------------------- #
# value rendering (source that reads exactly like a hand-written recipe)
# --------------------------------------------------------------------------- #

def _fmt(v) -> str:
    """Render a Python value as toolkit source: a string quoted, a tuple/list parenthesised, a number
    in its shortest exact spelling (int stays int, float via %g)."""
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, (tuple, list)):
        return "(" + ", ".join(_fmt(x) for x in v) + ")"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


# --------------------------------------------------------------------------- #
# the Op vocabulary — frozen, hashable, JSON-friendly
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AddElement:
    """`element = <kind>(<id>, *args)` — the root element (box/panel/stair/…)."""
    kind: str
    id: str
    args: tuple = ()

    def to_source(self) -> str:
        return f"element = {self.kind}(" + ", ".join([_fmt(self.id), *(_fmt(a) for a in self.args)]) + ")"


@dataclass(frozen=True)
class AddFeature:
    """`<func>(<target>, *args)` — a feature on an element (clearance_hole/hole/anchor/opening/section)."""
    func: str
    args: tuple = ()
    target: str = "element"

    def to_source(self) -> str:
        return f"{self.func}(" + ", ".join([self.target, *(_fmt(a) for a in self.args)]) + ")"


@dataclass(frozen=True)
class Place:
    """`place(<target>, (dx, dy, dz))` — position a part for an assembly."""
    target: str
    offset: tuple

    def to_source(self) -> str:
        return f"place({self.target}, {_fmt(tuple(self.offset))})"


@dataclass(frozen=True)
class Assemble:
    """`element = <kind>(<id>, *parts)` — combine named parts into an assembly."""
    id: str
    parts: tuple
    kind: str = "assembly"

    def to_source(self) -> str:
        return f"element = {self.kind}(" + ", ".join([_fmt(self.id), *self.parts]) + ")"


@dataclass(frozen=True)
class SetParam:
    """Edit a numeric parameter of an EXISTING program (a slider/face-drag as data). `apply` returns
    the new text and the inverse SetParam, so the edit is undoable."""
    name: str
    old: float
    new: float

    def to_source(self) -> str:
        return f"# set {self.name} = {_fmt(self.new)}"   # informational; apply() does the real work

    def apply(self, program: str):
        out = _substitute_all_literals(program, self.old, self.new)
        if out is None:
            return None, None
        return out, SetParam(self.name, self.new, self.old)


_OP_KINDS = {c.__name__: c for c in (AddElement, AddFeature, Place, Assemble, SetParam)}


@dataclass(frozen=True)
class Plan:
    """An ordered list of Ops. `render` writes the ADD ops to a fresh program (byte-identical to a
    hand-written recipe); `apply_to` threads the SetParam ops through an existing program and returns
    the inverse plan for undo."""
    ops: tuple = ()

    def render(self) -> str:
        lines = [op.to_source() for op in self.ops if not isinstance(op, SetParam)]
        return "\n".join(lines) + ("\n" if lines else "")

    def apply_to(self, program: str):
        out, inverse = program, []
        for op in self.ops:
            if isinstance(op, SetParam):
                new_text, inv = op.apply(out)
                if new_text is None:
                    continue
                out, _ = new_text, inverse.append(inv)
        return out, Plan(tuple(reversed(inverse)))


__all__ = ["AddElement", "AddFeature", "Place", "Assemble", "SetParam", "Plan",
           "_substitute_unique_literal", "_substitute_all_literals", "_comment_regions",
           "_substitute_constraint_value", "_substitute_hole_pos", "_NUM"]
