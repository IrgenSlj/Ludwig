"""Loop tests — execute/verify/repair driven by a MOCKED inference (no tokens, CI-safe)."""
import pytest

pytest.importorskip("cadquery")

from agent import inference, loop
from agent.loop import Brief

GOOD = """
element = box("bracket", 80, 40, 6)
clearance_hole(element, "M8", (-25, 0))
clearance_hole(element, "M8", (25, 0))
"""
WRONG_HEIGHT = 'element = box("bracket", 80, 40, 60)'


def test_strip_fences():
    assert loop._strip_fences("```python\nx = 1\n```") == "x = 1"
    assert loop._strip_fences("x = 1") == "x = 1"


def test_execute_builds_ir_and_forces_geometry():
    el, err = loop.execute(GOOD)
    assert err is None and el is not None
    from geometry import GeometryService
    _, _, height = GeometryService().bbox(el.geometry)
    assert abs(height - 6) < 1e-6
    assert el.geometry.built  # solid() was forced


def test_execute_reports_syntax_error():
    el, err = loop.execute("element = box('x', 10, 10")  # unbalanced parens
    assert el is None and err is not None


def test_execute_requires_element_binding():
    el, err = loop.execute("x = box('x', 10, 10, 10)")  # never assigns `element`
    assert el is None and "element" in err


def test_verify_flags_wrong_dimension():
    el, _ = loop.execute(WRONG_HEIGHT)
    crit = loop.verify(el, Brief(prompt="b", named_dims={"length": 80, "width": 40, "height": 6}, holes=0))
    assert not crit.passed
    assert any(c.check == "dim:height" for c in crit.failures)


def test_loop_repairs_a_wrong_first_pass(monkeypatch):
    seq = iter([WRONG_HEIGHT, GOOD])  # first generation wrong, repair correct
    monkeypatch.setattr(inference, "infer", lambda *a, **k: next(seq))
    res = loop.run(Brief(prompt="bracket", named_dims={"length": 80, "width": 40, "height": 6}, holes=2),
                   rounds=2)
    assert res.passed and res.rounds == 1


def test_run_with_zero_rounds_does_not_repair(monkeypatch):
    # first-pass semantics: one generation, no repair — a wrong program stays wrong
    monkeypatch.setattr(inference, "infer", lambda *a, **k: WRONG_HEIGHT)
    res = loop.run(Brief(prompt="b", named_dims={"length": 80, "width": 40, "height": 6}, holes=0),
                   rounds=0)
    assert res.rounds == 0 and not res.passed


def test_run_selects_the_passing_candidate(monkeypatch):
    seq = iter([WRONG_HEIGHT, GOOD, WRONG_HEIGHT])
    monkeypatch.setattr(inference, "infer", lambda *a, **k: next(seq))
    res = loop.run(Brief(prompt="bracket", named_dims={"length": 80, "width": 40, "height": 6}, holes=2),
                   candidates=3, rounds=0)
    assert res.passed and res.rounds == 0


def test_run_repairs_when_all_candidates_fail(monkeypatch):
    seq = iter([WRONG_HEIGHT, WRONG_HEIGHT, GOOD])
    monkeypatch.setattr(inference, "infer", lambda *a, **k: next(seq))
    res = loop.run(Brief(prompt="bracket", named_dims={"length": 80, "width": 40, "height": 6}, holes=2),
                   candidates=2, rounds=1)
    assert res.passed and res.rounds == 1


def test_edit_produces_a_minimal_diff(monkeypatch):
    import difflib
    base = ('element = box("bracket", 80, 40, 6)\n'
            'clearance_hole(element, "M8", (-25, 0))\n'
            'clearance_hole(element, "M8", (25, 0))\n')
    edited = base.replace("M8", "M10")  # a well-behaved model changes only the two hole lines
    monkeypatch.setattr(inference, "infer", lambda *a, **k: edited)
    res = loop.edit(base, "make the holes M10")
    assert res.ir is not None and res.passed
    changed = [ln for ln in difflib.unified_diff(base.splitlines(), res.program.splitlines())
               if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    assert len(changed) == 4  # exactly the two hole lines (2 removed + 2 added)
