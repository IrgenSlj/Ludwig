"""Manufacturing critic tests — cast-in anchor cover + min-wall (S10/P1). Require OCCT."""
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
    # min-wall check present
    assert any(c.check == "min_wall" for c in crit.checks)


def test_panel_anchor_too_close_fails():
    el = panel("p", 3000, 2000, 200)
    anchor(el, 17.5, (1495, 0), 150)
    crit = manufacturing.evaluate(el, None)
    assert not crit.passed
    # the cover check fails, but min-wall may still pass
    assert any(c.check.startswith("cover:") and c.status.name == "FAIL" for c in crit.checks)


def test_no_features_is_na():
    el = box("b", 80, 40, 6)
    crit = manufacturing.evaluate(el, None)
    assert crit.passed
    # box has no anchors (NA cover) but passes min-wall (6 mm >= 1.5 mm)
    assert any(c.check == "cover" and c.status.name == "NA" for c in crit.checks)
    assert any(c.check == "min_wall" and c.status.name == "PASS" for c in crit.checks)
