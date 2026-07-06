"""No-model tests for WS2 deliberative branch-and-prune search (docs/V2_ROADMAP.md §2, §5).

The driver's model/kernel primitives are injected, so the whole tree runs token-free with a scripted
mock: a "program" is `prog:<quality>` where lower quality is better and 0 passes the critic; a negative
quality is a build failure. `score` mirrors `agent.loop._weighted_failures`: build failure = (1, 0)
(worst), else (0, quality).
"""
from __future__ import annotations

import pytest

from agent.search import Candidate, plan_levels, search


# --------------------------------------------------------------------------- #
# scheduler math
# --------------------------------------------------------------------------- #
def test_plan_levels_unbounded_is_ideal():
    assert plan_levels(3, 3, 0.5) == [3, 3, 3]
    assert plan_levels(1, 4, 0.5) == [4]
    assert plan_levels(3, 3, 0.5, max_calls=100) == [3, 3, 3]   # ceiling doesn't bind


def test_plan_levels_budget_binds_and_respects_ratio():
    # ideal sum 9 > 5 → truncated; explore = round(5*(1-0.5)) = 2 (capped at branch), then refine.
    lv = plan_levels(3, 3, 0.5, max_calls=5)
    assert sum(lv) <= 5 and lv[0] == 2

    # higher veri_ratio → smaller explore share (more budget to refinement)
    explore_heavy = plan_levels(4, 4, 0.25, max_calls=10)
    refine_heavy = plan_levels(4, 4, 0.75, max_calls=10)
    assert sum(explore_heavy) <= 10 and sum(refine_heavy) <= 10
    assert explore_heavy[0] > refine_heavy[0]                    # 0.25 explores wider at level 0


def test_plan_levels_rejects_bad_shape():
    with pytest.raises(ValueError):
        plan_levels(0, 3, 0.5)
    with pytest.raises(ValueError):
        plan_levels(3, 0, 0.5)


# --------------------------------------------------------------------------- #
# scripted mock harness
# --------------------------------------------------------------------------- #
class _Crit:
    def __init__(self, quality: int) -> None:
        self.quality = quality
        self.passed = quality == 0
        self.failures: list = []


def _make_env(scripts):
    """Return (propose, refine, execute, verify, score, events) consuming `scripts` (qualities) in order."""
    it = iter(scripts)
    events: list[dict] = []

    def propose(_brief):
        return f"prog:{next(it)}"

    def refine(_parent, _brief):
        return f"prog:{next(it)}"

    def execute(program):
        q = int(program.split(":")[1])
        return (None, "build error") if q < 0 else (q, None)

    def verify(ir, _brief):
        return _Crit(ir)

    def score(crit):
        return (1, 0) if crit is None else (0, crit.quality)

    return propose, refine, execute, verify, score, events


def _run(scripts, *, depth, branch, keep_k=1, veri_ratio=0.5, max_calls=None):
    propose, refine, execute, verify, score, events = _make_env(scripts)
    res = search(None, depth=depth, branch=branch, keep_k=keep_k, veri_ratio=veri_ratio,
                 max_calls=max_calls, propose=propose, refine=refine, execute=execute,
                 verify=verify, score=score, on_event=events.append)
    return res, events


def test_converges_at_level0_when_a_proposal_passes():
    res, _ = _run([2, 0, 5], depth=3, branch=3)   # second proposal passes (q=0)
    assert res.passed and res.reason == "converged"
    assert res.calls_used == 3                     # stopped after level 0; refine scripts untouched
    assert res.best.score == (0, 0)


def test_refinement_improves_across_levels():
    # level0: [5,4,3] → best 3; level1: [2,6,1] → best 1; level2: [0,9,4] → best 0 → converge
    res, _ = _run([5, 4, 3, 2, 6, 1, 0, 9, 4], depth=3, branch=3)
    assert res.passed and res.reason == "converged"
    assert res.calls_used == 9
    assert res.best.program == "prog:0"


def test_beam_is_monotonic_never_regresses():
    # level0 best=3; level1 children all worse (7,8,9) → parent survives, best stays 3
    res, _ = _run([3, 4, 5, 7, 8, 9], depth=2, branch=3)
    assert not res.passed and res.reason == "exhausted"
    assert res.best.score == (0, 3) and res.best.program == "prog:3"


def test_build_failures_are_pruned():
    res, _ = _run([-1, 2, -1], depth=1, branch=3)  # only q=2 builds
    assert res.best.program == "prog:2" and res.best.score == (0, 2)


def test_budget_truncates_plan_and_reports_reason():
    # depth3 branch3 ideal=9 > 4 → plan [2,2]; none pass → reason budget
    res, _ = _run([5, 4, 3, 2], depth=3, branch=3, max_calls=4)
    assert res.reason == "budget"
    assert res.calls_used == 4 and res.levels == [2, 2]


def test_keep_k_beam_holds_multiple_survivors():
    # keep_k=2, branch=4: level0 [5,4,3,1] keeps {1,3}; level1 refines both (4 children [2,0,6,7])
    res, _ = _run([5, 4, 3, 1, 2, 0, 6, 7], depth=2, branch=4, keep_k=2)
    assert res.best.program == "prog:0" and res.passed


def test_event_stream_shape():
    _, events = _run([2, 0, 5], depth=3, branch=3)
    stages = [e["stage"] for e in events]
    assert stages[0] == "propose"
    assert "evaluate" in stages and "select" in stages
    assert stages[-1] == "terminal"
    assert events[-1]["reason"] == "converged"


def test_deterministic_replay_with_fixed_scripts():
    scripts = [5, 4, 3, 2, 6, 1, 0, 9, 4]
    res_a, ev_a = _run(scripts, depth=3, branch=3)
    res_b, ev_b = _run(scripts, depth=3, branch=3)
    assert res_a.best.program == res_b.best.program
    assert [e["stage"] for e in ev_a] == [e["stage"] for e in ev_b]
    assert res_a.calls_used == res_b.calls_used


def test_candidate_passed_property():
    assert Candidate("x", "prog:0", ir=0, critique=_Crit(0)).passed is True
    assert Candidate("x", "prog:1", ir=1, critique=_Crit(1)).passed is False
    assert Candidate("x", "", ir=None, critique=None).passed is False
