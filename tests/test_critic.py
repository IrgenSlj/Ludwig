"""Critic panel tests — the deterministic verifier (S4). Require the OCCT kernel."""
import types

import pytest

pytest.importorskip("cadquery")

from agent.loop import Brief, execute
from critic import panel
from critic.base import Critique

GOOD = """
element = box("bracket", 80, 40, 6)
clearance_hole(element, "M8", (-25, 0))
clearance_hole(element, "M8", (25, 0))
"""
WRONG_HEIGHT = 'element = box("bracket", 80, 40, 60)'  # height 60 ≠ 6, and no holes


def _brief():
    return Brief(prompt="bracket", named_dims={"length": 80, "width": 40, "height": 6}, holes=2)


def test_panel_passes_a_correct_bracket():
    el, err = execute(GOOD)
    assert err is None
    crit = panel.evaluate(el, _brief())
    assert crit.passed, [(c.check, c.status.value, c.message) for c in crit.checks]


def test_panel_runs_all_three_critics():
    el, _ = execute(GOOD)
    names = {c.check for c in panel.evaluate(el, _brief()).checks}
    assert "watertight_manifold" in names   # geometric
    assert "dim:length" in names            # dimensional
    assert "units_present" in names         # semantic


def test_panel_flags_the_right_checks():
    el, _ = execute(WRONG_HEIGHT)
    fails = {c.check for c in panel.evaluate(el, _brief()).failures}
    assert "dim:height" in fails            # wrong extent
    assert "hole_count" in fails            # 0 built vs 2 declared


def test_dimensional_critic_reads_registered_dims():
    """A declared dim that is NOT an axis-aligned extent must be verified against the manifest —
    register_dim has to be load-bearing for the verdict (it was silently ignored before)."""
    from critic import dimensional
    # Spacer with a central bore; the program registers the bore diameter as a named dim.
    src = ('element = box("spacer", 30, 30, 12)\n'
           'hole(element, 10.0, (0, 0), name="bore")\n')
    el, err = execute(src)
    assert err is None
    good = dimensional.evaluate(el, Brief(prompt="spacer", named_dims={"bore": 10.0}))
    assert good.passed, [(c.check, c.message) for c in good.checks]
    # A brief asking for a ⌀12 bore must FAIL against the ⌀10 that was built/registered.
    bad = dimensional.evaluate(el, Brief(prompt="spacer", named_dims={"bore": 12.0}))
    assert not bad.passed
    assert any(c.check == "dim:bore" for c in bad.failures)


def test_assembly_builds_through_the_loop():
    """assembly() must be reachable from a generated program (S12 deliverable); it was missing from
    the execute() namespace, so any codegen calling it died with NameError."""
    src = ('a = box("a", 20, 20, 5)\n'
           'b = box("b", 10, 10, 5)\n'
           'element = assembly("asm", a, b)\n')
    el, err = execute(src)
    assert err is None, err
    assert el.type == "Assembly"
    assert len(el.children) == 2
    assert el.geometry is not None


def test_stack_assembly_builds_through_the_loop():
    """The model can position parts with stack()/place() instead of hand-rolling a kernel translate —
    the seam that makes assembly codegen reliable. Seats top on base → union 60×60×20."""
    from geometry import GeometryService
    src = ('base = box("base", 60, 60, 10)\n'
           'top = box("top", 40, 40, 10)\n'
           'stack(base, top)\n'
           'element = assembly("stacked_plates", base, top)\n')
    el, err = execute(src)
    assert err is None, err
    assert el.type == "Assembly" and len(el.children) == 2
    length, width, height = GeometryService().bbox(el.geometry)
    assert (round(length), round(width), round(height)) == (60, 60, 20)  # top seated on base


def test_capabilities_gate_selects_critics():
    el, _ = execute(GOOD)
    # no critic applies to a capability set the panel doesn't cover → empty, vacuously passing
    crit = panel.evaluate(el, _brief(), capabilities={"ifc-only-nonexistent"})
    assert crit.checks == []


def test_register_adds_a_critic_without_touching_the_loop():
    before = len(panel.critics())
    fake = types.SimpleNamespace(name="fake", applies_to={"brep"},
                                 evaluate=lambda ir, brief: Critique())
    panel.register(fake)
    try:
        assert len(panel.critics()) == before + 1
    finally:
        panel._PANEL.pop()  # keep global panel clean for other tests
