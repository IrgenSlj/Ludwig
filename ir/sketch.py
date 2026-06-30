"""Sketch IR — 2D constrained geometry (R27). Pure Python, ZERO heavy deps (no kernel, no numpy).

A Sketch is points + entities (lines / circles) + constraints. The solver (geometry/sketch_solver.py)
finds the point coordinates that satisfy the constraints and reports the remaining degrees of freedom.
Constrained distance / radius dims surface as NamedDims so the critic and UI read them exactly like a
3D part's extents. Sketch → extrude is R28; the solver seam (planegcs as the industrial upgrade) is R27.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Point2D:
    id: str
    x: float = 0.0
    y: float = 0.0
    fixed: bool = False     # an anchored point — excluded from the solver's free variables (removes 2 DoF)


@dataclass
class Line:
    id: str
    p1: str                 # point id
    p2: str                 # point id


@dataclass
class Circle:
    id: str
    center: str             # point id
    radius: float = 1.0


@dataclass
class Constraint:
    """A solver constraint. kind ∈ coincident | horizontal | vertical | distance | radius | fix.
    refs are the point/line/circle ids it acts on; value is the target for distance/radius dims."""
    kind: str
    refs: tuple
    value: float | None = None


@dataclass
class Sketch:
    id: str
    points: dict = field(default_factory=dict)
    lines: dict = field(default_factory=dict)
    circles: dict = field(default_factory=dict)
    constraints: list = field(default_factory=list)

    # ---- fluent builders ----
    def point(self, pid: str, x: float = 0.0, y: float = 0.0, *, fixed: bool = False) -> Point2D:
        p = Point2D(pid, float(x), float(y), bool(fixed))
        self.points[pid] = p
        return p

    def line(self, lid: str, p1: str, p2: str) -> Line:
        ln = Line(lid, p1, p2)
        self.lines[lid] = ln
        return ln

    def circle(self, cid: str, center: str, radius: float = 1.0) -> Circle:
        c = Circle(cid, center, float(radius))
        self.circles[cid] = c
        return c

    def constrain(self, kind: str, *refs: str, value: float | None = None) -> Constraint:
        c = Constraint(kind, tuple(refs), None if value is None else float(value))
        self.constraints.append(c)
        return c

    def dims(self) -> list:
        """Distance / radius constraints as NamedDims — the dimensioned parameters of the sketch
        (what the UI exposes as editable, like a 3D part's extents). Imported lazily to stay dep-free."""
        from ir.elements import NamedDim
        out = []
        for c in self.constraints:
            if c.kind == "distance" and c.value is not None:
                out.append(NamedDim(f"d_{'_'.join(c.refs)}", c.value))
            elif c.kind == "radius" and c.value is not None:
                out.append(NamedDim(f"r_{'_'.join(c.refs)}", c.value))
        return out
