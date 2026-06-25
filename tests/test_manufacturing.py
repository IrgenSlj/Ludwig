"""Manufacturing critic tests — cast-in anchor cover (S10). Require the OCCT kernel."""
import pytest

pytest.importorskip("cadquery")

from toolkit import panel, anchor, box
from critic import manufacturing


def test_panel_anchor_cover_passes():
    el = panel("p", 3000, 2000, 200)
    anchor(el, 17.5, (-750, 0), 150)
    anchor(el, 17.5, (750, 0), 150)
    crit = manufacturing.evaluate(el, None)
    assert crit.passed, [(c.check, c.status.value, c.message) for c in crit.checks]
    assert sum(1 for c in crit.checks if c.check.startswith("cover:")) == 2


def test_panel_anchor_too_close_fails():
    el = panel("p", 3000, 2000, 200)
    anchor(el, 17.5, (1495, 0), 150)
    assert not manufacturing.evaluate(el, None).passed


def test_no_features_is_na():
    el = box("b", 80, 40, 6)
    crit = manufacturing.evaluate(el, None)
    assert crit.passed
