"""Pure-Python checks on the frozen brief set (no kernel needed)."""
from eval.briefs import BRIEFS


def test_brief_set_unique_and_wellformed():
    ids = [b["id"] for b in BRIEFS]
    assert len(ids) == len(set(ids)), "brief ids must be unique"
    for b in BRIEFS:
        assert {"id", "prompt", "dims", "holes"} <= set(b)
        assert set(b["dims"]) == {"length", "width", "height"}
        assert all(isinstance(v, float) for v in b["dims"].values())
        assert isinstance(b["holes"], int) and b["holes"] >= 0
