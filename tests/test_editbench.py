"""No-model, no-dataset tests for the BenchCAD edit-bench harness (B1, docs/BENCH_PLAN.md).

Everything here runs token-free. The pure-Python half (sampler, metric math, trust tripwire, run
driver) needs no kernel at all; the exact-IoU half is marked `kernel` and skips without cadquery,
matching the rest of the suite's posture.
"""
from __future__ import annotations

import pytest

from eval import benchcad, editbench


def _row(rid="r1", family="gear", orig="a = 1\nb = 2", gt="a = 1\nb = 3", iou=0.5):
    return {"record_id": rid, "family": family, "category": "T1",
            "category_label": "literal_replace", "instruction": "change b to 3",
            "iou": iou, "orig_code": orig, "gt_code": gt}


# --------------------------------------------------------------------------- #
# stratified sampling — a partial run must span families, not the first N rows
# --------------------------------------------------------------------------- #
def test_stratify_spreads_across_families():
    rows = [{"record_id": f"{f}_{i}", "family": f}
            for f in ("gear", "bolt", "cam", "spring") for i in range(5)]
    got = benchcad.stratify(rows, 4)
    assert len(got) == 4
    assert len({r["family"] for r in got}) == 4          # one per family, not 4 gears


def test_stratify_is_deterministic_and_seed_rotates():
    rows = [{"record_id": f"{f}_{i}", "family": f} for f in ("a", "b", "c") for i in range(3)]
    assert benchcad.stratify(rows, 2) == benchcad.stratify(rows, 2)
    assert benchcad.stratify(rows, 1, seed=1) != benchcad.stratify(rows, 1, seed=0)


def test_stratify_no_op_when_limit_covers_everything():
    rows = [{"record_id": "x", "family": "a"}, {"record_id": "y", "family": "b"}]
    assert benchcad.stratify(rows, None) is rows
    assert benchcad.stratify(rows, 10) is rows


def test_stratify_drains_uneven_buckets_without_looping_forever():
    rows = [{"record_id": "a0", "family": "a"}] + [
        {"record_id": f"b{i}", "family": "b"} for i in range(3)]
    got = benchcad.stratify(rows, 4)                      # more than 'a' can supply
    assert len(got) == 4


def test_families_counts():
    rows = [{"family": "a"}, {"family": "a"}, {"family": "b"}]
    assert benchcad.families(rows) == {"a": 2, "b": 1}


# --------------------------------------------------------------------------- #
# the metric
# --------------------------------------------------------------------------- #
def test_normalized_accuracy_is_headroom_relative():
    assert editbench.normalized_accuracy(0.6, 1.0) == 1.0        # landed the edit
    assert editbench.normalized_accuracy(0.6, 0.6) == 0.0        # no better than doing nothing
    assert editbench.normalized_accuracy(0.5, 0.75) == pytest.approx(0.5)


def test_normalized_accuracy_clamps_both_ends():
    assert editbench.normalized_accuracy(0.5, 0.1) == 0.0        # worse than the original
    assert editbench.normalized_accuracy(0.5, 1.5) == 1.0        # can't exceed the ground truth


def test_zero_headroom_demands_an_exact_match():
    """A row whose edit doesn't move the geometry must not hand out a free 1.0 for changing nothing."""
    assert editbench.normalized_accuracy(1.0, 1.0) == 1.0
    assert editbench.normalized_accuracy(1.0, 0.9) == 0.0


def test_diff_size_counts_changed_lines():
    assert editbench.diff_size("a\nb\nc", "a\nb\nc") == 0
    assert editbench.diff_size("a\nb\nc", "a\nX\nc") == 2        # one removed, one added
    assert editbench.diff_size("a", "a\nb") == 1


def test_diff_size_ignores_comment_bookkeeping_by_default():
    """65% of edit-bench's ground-truth diff lines are comment-only; counting them would flatter
    the minimal-diff claim on bookkeeping Ludwig never did."""
    before, after = "# w\nx = 1", "# w = 5\nx = 1"
    assert editbench.diff_size(before, after) == 0               # comment churn only
    assert editbench.diff_size(before, after, code_only=False) == 2
    assert editbench.diff_size(before, "# w = 5\nx = 2") == 2     # the code change still counts


def test_diff_size_ignores_blank_line_churn():
    assert editbench.diff_size("a\n\nb", "a\nb") == 0


# --------------------------------------------------------------------------- #
# the trust tripwire — a tripwire, NOT a sandbox (see the module docstring)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("src", [
    "import os",
    "import subprocess as sp",
    "from pathlib import Path",
    "__import__('os')",
    "open('/etc/passwd')",
    "eval('1+1')",
    "x = (1).__class__",
])
def test_screen_refuses_non_cad_programs(src):
    with pytest.raises(editbench.ScreenError):
        editbench.screen(src)


@pytest.mark.parametrize("src", [
    "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 2, 3)",
    "import math\nimport cadquery as cq\nresult = cq.Workplane('XY').cylinder(math.pi, 2)",
    "from cadquery import Workplane\nresult = Workplane('XY').box(1, 1, 1)\nshow_object(result)",
])
def test_screen_allows_real_cad_programs(src):
    editbench.screen(src)                                        # must not raise


def test_screen_propagates_a_syntax_error():
    with pytest.raises(SyntaxError):
        editbench.screen("def (:")


# --------------------------------------------------------------------------- #
# summarize — ungradeable rows leave the denominator
# --------------------------------------------------------------------------- #
def test_summarize_excludes_ungradeable_from_the_denominator():
    results = [
        {"family": "a", "exec_ok": True, "error": None, "ungradeable": None,
         "score": 1.0, "diff_lines": 2, "gt_diff_lines": 2},
        {"family": "b", "exec_ok": False, "error": None, "ungradeable": "kernel unreliable",
         "score": 0.0, "diff_lines": 0, "gt_diff_lines": 4},
    ]
    s = editbench.summarize(results)
    assert s["n"] == 1 and s["ungradeable"] == 1
    assert s["normalized_accuracy"] == 1.0                       # NOT 0.5 — the bad row is not a miss
    assert s["exec_rate"] == 1.0


def test_summarize_diff_ratio_is_a_median_over_graded_rows():
    def r(score, diff, gt_diff):
        return {"family": "a", "exec_ok": True, "error": None, "ungradeable": None,
                "score": score, "diff_lines": diff, "gt_diff_lines": gt_diff}
    # ratios 1.0, 1.0, 50.0 — the median ignores the one rewrite, the mean would not
    s = editbench.summarize([r(1.0, 2, 2), r(1.0, 4, 4), r(0.0, 100, 2)])
    assert s["diff_ratio_median"] == 1.0
    assert s["exact_rate"] == pytest.approx(2 / 3)


def test_summarize_of_nothing_is_zeroed_not_a_crash():
    s = editbench.summarize([])
    assert s["n"] == 0 and s["normalized_accuracy"] == 0.0 and s["diff_ratio_median"] == 0.0


# --------------------------------------------------------------------------- #
# the run driver
# --------------------------------------------------------------------------- #
def test_run_treats_a_raising_predictor_as_a_miss_not_a_crash():
    def boom(_row):
        raise RuntimeError("model exploded")

    summary, results = editbench.run([_row()], boom)
    assert summary["n"] == 1 and results[0]["exec_ok"] is False
    assert "model exploded" in results[0]["error"]


def test_predict_oracle_and_noop_return_the_reference_programs():
    row = _row()
    assert editbench.predict_oracle(row) == row["gt_code"]
    assert editbench.predict_noop(row) == row["orig_code"]


# --------------------------------------------------------------------------- #
# exact IoU (needs the OCCT kernel)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def geom():
    pytest.importorskip("cadquery")
    from geometry import GeometryService
    return GeometryService()


def test_iou_of_a_shape_against_itself_is_exactly_one(geom):
    """The coincident-face case OCCT's boolean handles worst, and the one a correct edit produces."""
    box = geom.box(20, 10, 5)
    assert geom.iou(box, box) == 1.0
    assert geom.iou(box, geom.box(20, 10, 5)) == 1.0             # separately built, same shape


def test_iou_of_disjoint_solids_is_zero(geom):
    a = geom.box(10, 10, 10)
    b = geom.translate(geom.box(10, 10, 10), (100.0, 0.0, 0.0))
    assert geom.iou(a, b) == 0.0


def test_iou_of_a_half_overlap_is_one_third(geom):
    """Two unit boxes offset by half: intersection 1/2, union 3/2 → IoU 1/3."""
    a = geom.box(10, 10, 10)
    b = geom.translate(geom.box(10, 10, 10), (5.0, 0.0, 0.0))
    assert geom.iou(a, b) == pytest.approx(1 / 3, rel=1e-6)


def test_iou_is_symmetric(geom):
    a = geom.box(10, 10, 10)
    b = geom.translate(geom.box(6, 6, 6), (2.0, 0.0, 0.0))
    assert geom.iou(a, b) == pytest.approx(geom.iou(b, a))


def test_congruence_is_not_fooled_by_a_symmetric_reposition(geom):
    """The rib_plate defect: moving a symmetric array preserves volume, bbox AND centroid.

    Only the inertia tensor separates these, so without it the grader hands out a free 1.0 for an
    edit that changed nothing. Regression for FINDINGS §B1 defect 3.
    """
    near = geom.slot(geom.slot(geom.box(100, 40, 10), 4, 20, (-20.0, 0.0)), 4, 20, (20.0, 0.0))
    far = geom.slot(geom.slot(geom.box(100, 40, 10), 4, 20, (-40.0, 0.0)), 4, 20, (40.0, 0.0))
    assert geom.volume(near) == pytest.approx(geom.volume(far))   # same volume
    assert geom.bbox(near) == geom.bbox(far)                      # same bbox
    assert 0.0 < geom.iou(near, far) < 1.0                        # …but not the same shape


def test_iou_handles_a_multi_solid_compound(geom):
    """The ball_knob defect: an unfused/tangent compound scored IoU 0.247 against itself."""
    c = geom.compound([geom.box(10, 10, 10),
                       geom.translate(geom.box(10, 10, 10), (50.0, 0.0, 0.0))])
    assert geom.iou(c, c) == 1.0
