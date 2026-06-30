"""Sketch constraint solver tests (R27) — pure-Python, no kernel required."""
from geometry.sketch_solver import NumericSolver, solve
from ir.sketch import Sketch


def _rect(dims=True):
    s = Sketch("r")
    s.point("a", 0, 0, fixed=True)
    s.point("b", 35, 3); s.point("c", 33, 18); s.point("d", 2, 19)
    for lid, p, q in [("L0", "a", "b"), ("L1", "b", "c"), ("L2", "c", "d"), ("L3", "d", "a")]:
        s.line(lid, p, q)
    s.constrain("horizontal", "L0"); s.constrain("vertical", "L1")
    s.constrain("horizontal", "L2"); s.constrain("vertical", "L3")
    if dims:
        s.constrain("distance", "L0", value=40); s.constrain("distance", "L1", value=20)
    return s


def test_fully_constrained_rectangle_solves_exactly():
    r = solve(_rect(True))
    assert r.solved and r.dof == 0
    want = {"a": (0, 0), "b": (40, 0), "c": (40, 20), "d": (0, 20)}
    for k, (wx, wy) in want.items():
        x, y = r.coords[k]
        assert abs(x - wx) < 1e-6 and abs(y - wy) < 1e-6, (k, r.coords[k])
    assert {d.name: d.value for d in r.dims} == {"d_L0": 40.0, "d_L1": 20.0}


def test_under_constrained_reports_remaining_dof():
    assert solve(_rect(False)).dof == 2          # width + height free


def test_over_constrained_distance_still_reports_zero_dof():
    # add a redundant distance equal to the diagonal-consistent value — no extra DoF removed
    s = _rect(True)
    s.constrain("distance", "L2", value=40)      # L2 horizontal == L0 == 40 (consistent, redundant)
    r = solve(s)
    assert r.dof == 0 and r.solved


def test_solver_writes_solution_back_into_the_sketch():
    s = _rect(True)
    NumericSolver().solve(s)
    assert abs(s.points["c"].x - 40) < 1e-6 and abs(s.points["c"].y - 20) < 1e-6


def test_distance_between_two_points_constraint():
    import math
    s = Sketch("seg")
    s.point("p", 0, 0, fixed=True)
    s.point("q", 3, 4)
    s.constrain("distance", "p", "q", value=10)              # point-pair distance form
    r = solve(s)
    assert abs(math.hypot(*r.coords["q"]) - 10) < 1e-6       # q lands at distance 10 from the origin
    assert r.dof == 1                                        # 1 constraint on 2 free vars → direction free
