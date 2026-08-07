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

import dataclasses
import json as _json
import keyword
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
    in its shortest exact spelling (int stays int, float via %g).

    Strings go through `json.dumps`, not an f-string — the rendered program is `exec`'d downstream, so
    an unescaped `"` in a value would close the literal and turn DATA into CODE. json.dumps emits a
    double-quoted, fully-escaped literal that Python parses identically (the recipe's house style).
    Anything that is not a str/number/sequence is refused rather than `str()`-ed into source.
    """
    if isinstance(v, str):
        return _json.dumps(v)
    if isinstance(v, (tuple, list)):
        return "(" + ", ".join(_fmt(x) for x in v) + ")"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, int):
        return str(v)
    raise ValueError(f"cannot render {type(v).__name__} as toolkit source (ops carry data, not objects)")


# --------------------------------------------------------------------------- #
# name validation — the other half of the boundary
# --------------------------------------------------------------------------- #
#
# `_fmt` protects values that are rendered as string LITERALS. These names are rendered as bare
# source tokens — a callable (`box(...)`) or a variable reference (`place(top, ...)`) — so they are
# never quoted and must be constrained to what they claim to be. Without this an `op` kind of
# `__import__('os').system('…') or box` renders straight into the program the loop exec's.

# The callable subset of `agent.loop.execute`'s namespace: the verbs a recipe may name. Modules and
# types in that namespace (cq/cadquery/standards/Element) are deliberately absent — they are not ops.
# `tests/test_ops.py::test_callable_allowlist_matches_the_execute_namespace` guards the two from drifting.
_CALLABLES = frozenset({
    "part", "box", "cylinder", "hole", "clearance_hole", "panel", "anchor", "assembly", "place",
    "stack", "profile", "stair", "wall", "opening", "sketch", "extrude", "section", "fillet",
    "chamfer", "slot", "counterbore",
})

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _callable_name(value, field: str) -> str:
    """A toolkit verb this op may render as a call. Allowlisted, so nothing else can be named."""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a str, got {type(value).__name__}")
    if value not in _CALLABLES:
        raise ValueError(f"unknown {field} {value!r} (allowed: {', '.join(sorted(_CALLABLES))})")
    return value


def _ident(value, field: str) -> str:
    """A bare variable reference rendered unquoted into source — must be a plain identifier."""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a str, got {type(value).__name__}")
    if not _IDENT.match(value) or keyword.iskeyword(value) or value.startswith("__"):
        raise ValueError(f"{field} must be a plain identifier, got {value!r}")
    return value


def _data(value, field: str):
    """A value carried as DATA into a rendered literal. Scalars and nested sequences only — a dict
    would both break the frozen Op's hashability and render as something no recipe ever writes."""
    if isinstance(value, (list, tuple)):
        return tuple(_data(x, field) for x in value)
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} may only carry numbers, strings and nested lists, "
                     f"got {type(value).__name__}")


# --------------------------------------------------------------------------- #
# the Op vocabulary — frozen, hashable, JSON-friendly
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AddElement:
    """`element = <kind>(<id>, *args)` — the root element (box/panel/stair/…)."""
    kind: str
    id: str
    args: tuple = ()

    def __post_init__(self):
        _callable_name(self.kind, "AddElement.kind")
        object.__setattr__(self, "id", _data(self.id, "AddElement.id"))
        object.__setattr__(self, "args", _data(tuple(self.args), "AddElement.args"))

    def to_source(self) -> str:
        return f"element = {self.kind}(" + ", ".join([_fmt(self.id), *(_fmt(a) for a in self.args)]) + ")"


@dataclass(frozen=True)
class AddFeature:
    """`<func>(<target>, *args)` — a feature on an element (clearance_hole/hole/anchor/opening/section)."""
    func: str
    args: tuple = ()
    target: str = "element"

    def __post_init__(self):
        _callable_name(self.func, "AddFeature.func")
        _ident(self.target, "AddFeature.target")
        object.__setattr__(self, "args", _data(tuple(self.args), "AddFeature.args"))

    def to_source(self) -> str:
        return f"{self.func}(" + ", ".join([self.target, *(_fmt(a) for a in self.args)]) + ")"


@dataclass(frozen=True)
class Place:
    """`place(<target>, (dx, dy, dz))` — position a part for an assembly."""
    target: str
    offset: tuple

    def __post_init__(self):
        _ident(self.target, "Place.target")
        object.__setattr__(self, "offset", _data(tuple(self.offset), "Place.offset"))

    def to_source(self) -> str:
        return f"place({self.target}, {_fmt(tuple(self.offset))})"


@dataclass(frozen=True)
class Assemble:
    """`element = <kind>(<id>, *parts)` — combine named parts into an assembly."""
    id: str
    parts: tuple
    kind: str = "assembly"

    def __post_init__(self):
        _callable_name(self.kind, "Assemble.kind")
        object.__setattr__(self, "id", _data(self.id, "Assemble.id"))
        # parts are rendered UNQUOTED — they name variables in the program, not string values.
        object.__setattr__(self, "parts", tuple(_ident(p, "Assemble.parts[]") for p in self.parts))

    def to_source(self) -> str:
        return f"element = {self.kind}(" + ", ".join([_fmt(self.id), *self.parts]) + ")"


@dataclass(frozen=True)
class SetParam:
    """Edit a numeric parameter of an EXISTING program (a slider/face-drag as data). `apply` returns
    the new text and the inverse SetParam, so the edit is undoable."""
    name: str
    old: float
    new: float

    def __post_init__(self):
        # `parse_plan` accepts a numeric STRING for old/new (models emit "80" as often as 80), but
        # every consumer does arithmetic on them — coerce once here so `apply` can't TypeError on an
        # input the validator called valid.
        for f in ("old", "new"):
            v = getattr(self, f)
            if isinstance(v, bool) or not isinstance(v, (int, float, str)):
                raise ValueError(f"SetParam.{f} must be a number, got {type(v).__name__}")
            try:
                object.__setattr__(self, f, float(v))
            except (TypeError, ValueError) as e:
                raise ValueError(f"SetParam.{f} must be a number, got {v!r}") from e
        if not isinstance(self.name, str) or "\n" in self.name:
            raise ValueError(f"SetParam.name must be a single-line str, got {self.name!r}")

    def to_source(self) -> str:
        return f"# set {self.name} = {_fmt(self.new)}"   # informational; apply() does the real work

    def apply(self, program: str):
        out = _substitute_all_literals(program, self.old, self.new)
        if out is None:
            return None, None
        # Collision guard: if `new` already exists as a distinct literal in the original program,
        # the inverse SetParam would corrupt those pre-existing occurrences on undo.
        if abs(self.new - self.old) > 1e-9:
            comments = _comment_regions(program)
            in_comment = lambda pos: any(a <= pos < b for a, b in comments)  # noqa: E731
            collisions = [m for m in _NUM.finditer(program)
                          if abs(float(m.group()) - self.new) < 1e-9
                          and not in_comment(m.start())
                          and abs(float(m.group()) - self.old) >= 1e-9]
            if collisions:
                raise ValueError(
                    f"SetParam {self.name!r}: new={self.new} already occurs as a distinct literal "
                    "in the program — edit is non-invertible"
                )
        return out, SetParam(self.name, self.new, self.old)


_OP_KINDS = {c.__name__: c for c in (AddElement, AddFeature, Place, Assemble, SetParam)}


@dataclass(frozen=True)
class Plan:
    """An ordered list of Ops. `render` writes the ADD ops to a fresh program (byte-identical to a
    hand-written recipe); `apply_to` threads the SetParam ops through an existing program and returns
    the inverse plan for undo. The returned inverse plan carries a `.skipped` tuple of any SetParam
    ops that could not be applied (literal absent), so the caller can distinguish applied from skipped."""
    ops: tuple = ()
    skipped: tuple = ()   # ops that were not applied (e.g., literal not found in program)

    def render(self) -> str:
        lines = [op.to_source() for op in self.ops if not isinstance(op, SetParam)]
        return "\n".join(lines) + ("\n" if lines else "")

    def apply_to(self, program: str):
        out, inverse, skipped_ops = program, [], []
        for op in self.ops:
            if isinstance(op, SetParam):
                new_text, inv = op.apply(out)
                if new_text is None:
                    skipped_ops.append(op)
                    continue
                inverse.append(inv)
                out = new_text
        return out, Plan(tuple(reversed(inverse)), skipped=tuple(skipped_ops))


# --------------------------------------------------------------------------- #
# parse + validate JSON ops (R16) — the security boundary: data in, never code exec'd
# --------------------------------------------------------------------------- #

def parse_plan(data) -> Plan:
    """Strictly validate JSON op-data into a Plan. Accepts a list of op dicts or `{"ops": [...]}`.

    This is the security boundary of the Op-API, and it has TWO layers, because the rendered plan is
    exec'd downstream:

    1. **Shape** (here): only known Ops, with exactly their declared fields — an unknown `op` kind, an
       unexpected field, a missing required field, or a bad value type RAISES. JSON arrays become
       tuples so the frozen Ops stay hashable.
    2. **Content** (each Op's `__post_init__`): fields that render as bare source tokens
       (`kind`/`func`/`target`/`parts`) must be an allowlisted toolkit verb or a plain identifier, and
       fields that render as literals must be data `_fmt` can escape. Shape alone is NOT enough — a
       `kind` of `__import__('os').system('…') or box` is a well-shaped string that would otherwise
       render straight into the program. Because the check lives on the dataclass, it holds for every
       construction path (this parser, the MCP tools, the runtime planner, direct construction).
    """
    if isinstance(data, dict) and "ops" in data:
        data = data["ops"]
    if not isinstance(data, list):
        raise ValueError("plan must be a JSON list of ops (or an object with an 'ops' list)")

    def _tuplify(v):
        return tuple(_tuplify(x) for x in v) if isinstance(v, list) else v

    ops = []
    for i, raw in enumerate(data):
        if not isinstance(raw, dict) or "op" not in raw:
            raise ValueError(f"op[{i}] must be an object with an 'op' kind")
        cls = _OP_KINDS.get(raw["op"])
        if cls is None:
            raise ValueError(f"op[{i}]: unknown op kind {raw['op']!r} (allowed: {sorted(_OP_KINDS)})")
        fields = dataclasses.fields(cls)
        names = {f.name for f in fields}
        given = {k: v for k, v in raw.items() if k != "op"}
        extra = set(given) - names
        if extra:
            raise ValueError(f"op[{i}] ({raw['op']}): unexpected field(s) {sorted(extra)}")
        required = {f.name for f in fields
                    if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
        missing = required - set(given)
        if missing:
            raise ValueError(f"op[{i}] ({raw['op']}): missing field(s) {sorted(missing)}")
        # Per-field VALUE type validation (security boundary: reject non-data shapes before construction)
        _str_fields: dict[str, set] = {
            "AddElement": {"kind", "id"},
            "AddFeature": {"func", "target"},
            "Place": {"target"},
            "Assemble": {"id", "kind"},
            "SetParam": {"name"},
        }
        for _fname in _str_fields.get(raw["op"], set()):
            if _fname in given and not isinstance(given[_fname], str):
                raise ValueError(
                    f"op[{i}] ({raw['op']}): field '{_fname}' must be a str, "
                    f"got {type(given[_fname]).__name__!r}"
                )
        if raw["op"] == "SetParam":
            for _fname in ("old", "new"):
                _fv = given.get(_fname)
                if _fv is None:
                    continue   # missing field already caught above
                if isinstance(_fv, bool) or isinstance(_fv, (list, dict)):
                    raise ValueError(
                        f"op[{i}] (SetParam): field '{_fname}' must be a number or numeric string, "
                        f"got {type(_fv).__name__!r}"
                    )
                if isinstance(_fv, str):
                    try:
                        float(_fv)
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"op[{i}] (SetParam): field '{_fname}' must be a number or numeric string, "
                            f"got {_fv!r}"
                        )
        try:
            ops.append(cls(**{k: _tuplify(v) for k, v in given.items()}))
        except TypeError as e:
            raise ValueError(f"op[{i}] ({raw['op']}): {e}") from e
    return Plan(tuple(ops))


def summarize(op) -> str:
    """A one-line human summary of an Op — what `cli --plan` prints for review before `--apply`."""
    if isinstance(op, AddElement):
        return f"add {op.kind} '{op.id}' " + "×".join(_fmt(a) for a in op.args)
    if isinstance(op, AddFeature):
        return f"add {op.func} " + ", ".join(_fmt(a) for a in op.args)
    if isinstance(op, SetParam):
        return f"set {op.name}: {_fmt(op.old)} → {_fmt(op.new)}"
    if isinstance(op, Place):
        return f"place {op.target} by {_fmt(tuple(op.offset))}"
    if isinstance(op, Assemble):
        return f"assemble '{op.id}' from {', '.join(op.parts)}"
    return type(op).__name__


def extract_json(text: str):
    """Pull the JSON plan out of an LLM reply — a fenced ```json block if present, else the outermost
    array/object. Raises if none parses (so a non-JSON reply fails loud, never runs)."""
    m = re.search(r"```(?:json)?\s*(\[.*\]|\{.*\})\s*```", text, re.DOTALL)
    if m:
        try:
            return _json.loads(m.group(1))
        except ValueError:
            pass
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j > i:
            try:
                return _json.loads(text[i:j + 1])
            except ValueError:
                continue
    raise ValueError("no JSON plan found in the response")


__all__ = ["AddElement", "AddFeature", "Place", "Assemble", "SetParam", "Plan",
           "parse_plan", "extract_json", "summarize",
           "_substitute_unique_literal", "_substitute_all_literals", "_comment_regions",
           "_substitute_constraint_value", "_substitute_hole_pos", "_NUM"]
