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
