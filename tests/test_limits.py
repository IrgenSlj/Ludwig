import shutil
from pathlib import Path

import pytest

from ludwig.rules import limits
from ludwig.rules.packs import load_pack

PACKS = Path(__file__).resolve().parent.parent / "packs"
DEMO = Path(__file__).resolve().parent / "packs" / "demo"


@pytest.fixture
def pack(tmp_path):
    shutil.copytree(PACKS / "joinery-nl", tmp_path / "joinery-nl")
    return load_pack(tmp_path / "joinery-nl")


def test_reads_values_notes_and_users(pack):
    found = {x.path: x for x in limits.read(pack)}
    width = found["reconcile.width_tolerance_mm"]
    assert (width.value, width.line, width.used_by) == (1, 5, ["erp-width"])
    assert width.note.startswith("drawings and production may differ")
    demo = {x.path: x.used_by for x in limits.read(load_pack(DEMO))}
    assert demo["sash.max_width_mm"] == ["sash-width-max"]


def test_update_keeps_comments_and_changes_the_verdict_input(pack):
    before = (pack.root / "limits.yaml").read_text()
    new = limits.update(pack, {"reconcile.width_tolerance_mm": 2.5})
    after = (pack.root / "limits.yaml").read_text()
    assert after == before.replace("width_tolerance_mm: 1  #", "width_tolerance_mm: 2.5  #")
    rule = next(r for r in new.rules if r.id == "erp-width")
    assert rule.tolerance == 2.5 and new.content_hash != pack.content_hash


@pytest.mark.parametrize(("values", "problem"), [
    ({"reconcile.nope": 1}, "unknown limits"),
    ({"reconcile.width_tolerance_mm": "wide"}, "a number is needed"),
    ({"reconcile.width_tolerance_mm": -1}, "must be a number >= 0"),
])  # fmt: skip
def test_bad_updates_change_nothing(pack, values, problem):
    before = (pack.root / "limits.yaml").read_text()
    with pytest.raises(ValueError, match=problem):
        limits.update(pack, values)
    assert (pack.root / "limits.yaml").read_text() == before


def test_tolerance_may_name_a_limit_and_is_checked(tmp_path):
    (tmp_path / "pack.yaml").write_text("name: t\nversion: '1'\n")
    (tmp_path / "limits.yaml").write_text("t: {w: 2}\n")
    rule = ("- id: w\n  kind: compare\n  left: architect.width_mm\n  right: erp.width_mm\n"
            "  severity: blocker\n  tolerance: {}\n")  # fmt: skip
    (tmp_path / "checks.yaml").write_text(rule.format("limits.t.w"))
    assert load_pack(tmp_path).rules[0].tolerance == 2.0
    from ludwig.rules.packs import PackError

    (tmp_path / "checks.yaml").write_text(rule.format("limits.t.x"))
    with pytest.raises(PackError, match="unknown limit"):
        load_pack(tmp_path)
