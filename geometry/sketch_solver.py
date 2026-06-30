"""Sketch constraint solver (R27) — finds point coordinates satisfying a Sketch's constraints and
reports remaining degrees of freedom.

`SketchSolver` is the seam; `NumericSolver` is the default: it uses `scipy.optimize.least_squares` when
present, else a pure-Python damped Gauss-Newton (so `--selftest` stays green before any heavy dep). DoF
is `n_free_vars − rank(Jacobian)` at the solution. planegcs (LGPL) is the documented industrial upgrade
behind this seam; no GPL SolveSpace is pulled in-process.

Constraints (residual = 0 when satisfied):
  coincident(pA, pB)      → xA−xB, yA−yB
  horizontal(line)        → y2 − y1
  vertical(line)          → x2 − x1
  distance(line, value)   → |p2 − p1| − value     (also distance(pA, pB, value))
  fix(point)              → point excluded from variables (preferred) — also accepted as a residual
A `radius` dim is carried as a NamedDim (the circle radius is a parameter, not a coordinate variable).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class SolveResult:
    coords: dict                       # point_id -> (x, y) at the solution
    dof: int                           # remaining degrees of freedom (0 = fully constrained)
    residual_norm: float               # max |residual| at the solution
    solved: bool                       # residual_norm within tolerance
    dims: list = field(default_factory=list)   # distance/radius NamedDims


@runtime_checkable
class SketchSolver(Protocol):
    def solve(self, sketch) -> SolveResult: ...


# --------------------------------------------------------------------------- residuals / packing

def _free_index(sketch):
    """Map each non-fixed point to its (xi, yi) slot in the flat variable vector; return (index, x0)."""
    index, x0 = {}, []
    for pid, p in sketch.points.items():
        if p.fixed:
            continue
        index[pid] = (len(x0), len(x0) + 1)
        x0 += [p.x, p.y]
    return index, x0


def _coords(sketch, index, x):
    out = {}
    for pid, p in sketch.points.items():
        if p.fixed:
            out[pid] = (p.x, p.y)
        else:
            i, j = index[pid]
            out[pid] = (x[i], x[j])
    return out


def _residuals(sketch, coords):
    r = []
    for c in sketch.constraints:
        k = c.kind
        if k == "coincident":
            a, b = c.refs
            r += [coords[a][0] - coords[b][0], coords[a][1] - coords[b][1]]
        elif k == "horizontal":
            ln = sketch.lines[c.refs[0]]
            r.append(coords[ln.p2][1] - coords[ln.p1][1])
        elif k == "vertical":
            ln = sketch.lines[c.refs[0]]
            r.append(coords[ln.p2][0] - coords[ln.p1][0])
        elif k == "distance":
            if c.refs[0] in sketch.lines:
                ln = sketch.lines[c.refs[0]]
                p1, p2 = ln.p1, ln.p2
            else:
                p1, p2 = c.refs[0], c.refs[1]
            dx = coords[p2][0] - coords[p1][0]
            dy = coords[p2][1] - coords[p1][1]
            r.append(math.hypot(dx, dy) - c.value)
        elif k == "fix":
            p = sketch.points[c.refs[0]]
            if not p.fixed:    # a fix on a free point still removes its DoF
                r += [coords[c.refs[0]][0] - p.x, coords[c.refs[0]][1] - p.y]
        # radius is a dim, not a coordinate residual
    return r


# --------------------------------------------------------------------------- pure-Python linear algebra

def _transpose(M):
    return [list(col) for col in zip(*M)] if M else []


def _matmul(A, B):
    Bt = _transpose(B)
    return [[sum(a * b for a, b in zip(row, col)) for col in Bt] for row in A]


def _matvec(A, v):
    return [sum(a * x for a, x in zip(row, v)) for row in A]


def _jacobian(f, x, r0, eps=1e-7):
    m, n = len(r0), len(x)
    J = [[0.0] * n for _ in range(m)]
    for j in range(n):
        xj = x[j]
        x[j] = xj + eps
        r1 = f(x)
        x[j] = xj
        for i in range(m):
            J[i][j] = (r1[i] - r0[i]) / eps
    return J


def _solve_linear(A, b):
    """Gauss-Jordan solve A x = b for a square A; None if singular."""
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for r in range(n):
            if r != col and M[r][col] != 0.0:
                f = M[r][col] / pv
                for k in range(col, n + 1):
                    M[r][k] -= f * M[col][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def _rank(M, eps=1e-6):
    """Numerical rank via Gaussian elimination with partial pivoting."""
    A = [list(row) for row in M]
    rows = len(A)
    cols = len(A[0]) if A else 0
    rank, pr = 0, 0
    for c in range(cols):
        if pr >= rows:
            break
        piv = max(range(pr, rows), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < eps:
            continue
        A[pr], A[piv] = A[piv], A[pr]
        pv = A[pr][c]
        for r in range(rows):
            if r != pr and abs(A[r][c]) > eps:
                f = A[r][c] / pv
                for k in range(cols):
                    A[r][k] -= f * A[pr][k]
        pr += 1
        rank += 1
    return rank


def _gauss_newton(f, x0, iters=200, tol=1e-12):
    x = list(x0)
    if not x:
        return x
    for _ in range(iters):
        r = f(x)
        if not r:
            break
        if max(abs(v) for v in r) < tol:
            break
        J = _jacobian(f, x, r)
        Jt = _transpose(J)
        JtJ = _matmul(Jt, J)
        for k in range(len(x)):
            JtJ[k][k] += 1e-10                # tiny Levenberg damping for conditioning
        dx = _solve_linear(JtJ, [-v for v in _matvec(Jt, r)])
        if dx is None:
            break
        x = [xi + dxi for xi, dxi in zip(x, dx)]
    return x


class NumericSolver:
    """Default solver — scipy.least_squares when available, else pure-Python damped Gauss-Newton."""

    def solve(self, sketch, tol: float = 1e-6) -> SolveResult:
        index, x0 = _free_index(sketch)

        def f(x):
            return _residuals(sketch, _coords(sketch, index, x))

        if x0:
            try:
                from scipy.optimize import least_squares  # noqa: PLC0415
                x = [float(v) for v in least_squares(lambda v: f(list(v)) or [0.0],
                                                     x0, xtol=1e-14, ftol=1e-14).x]
                x = _gauss_newton(f, x)   # polish to machine precision (scipy stops near ~1e-9)
            except Exception:
                x = _gauss_newton(f, x0)
        else:
            x = []

        coords = _coords(sketch, index, x)
        for pid, (px, py) in coords.items():     # write the solution back into the sketch
            sketch.points[pid].x, sketch.points[pid].y = px, py

        r = f(x)
        res_norm = max((abs(v) for v in r), default=0.0)
        # DoF = free variables - independent constraints (rank of the Jacobian at the solution)
        rank = _rank(_jacobian(f, x, r)) if (x and r) else 0
        dof = len(x) - rank
        return SolveResult(coords=coords, dof=dof, residual_norm=res_norm,
                           solved=res_norm < tol, dims=sketch.dims())


def solve(sketch, *, solver: SketchSolver | None = None, tol: float = 1e-6) -> SolveResult:
    """Solve a sketch with the default (or a provided) solver."""
    return (solver or NumericSolver()).solve(sketch, tol)


__all__ = ["NumericSolver", "SketchSolver", "SolveResult", "solve"]
