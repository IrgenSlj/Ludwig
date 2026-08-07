"""Spend-gate tests (agent/budget.py) — pure Python, no kernel, no tokens.

The gate exists because `--eval --bench edit --live` defaults to the full 748-row set at the best
tier. These tests pin the two properties that make it worth having: the call count is exact, and the
refusal actually refuses.
"""
import io

import pytest

from agent import budget


def _rows(n, code_len=800, instr_len=60):
    return [{"record_id": f"r{i}", "orig_code": "x" * code_len, "instruction": "y" * instr_len}
            for i in range(n)]


def test_call_count_is_exact_arithmetic_not_an_estimate():
    # Dollars are an estimate; the call ceiling is not. rows x (1 + rounds).
    assert budget.project_edit_bench(_rows(10), rounds=0)["calls"] == 10
    assert budget.project_edit_bench(_rows(10), rounds=1)["calls"] == 20
    assert budget.project_edit_bench(_rows(748), rounds=2)["calls"] == 2244


def test_projection_scales_with_the_actual_prompt_text():
    # Sized from the rows we will send, not a per-call constant — a set of big programs must project
    # higher than the same number of small ones.
    small = budget.project_edit_bench(_rows(20, code_len=300), rounds=1)
    big = budget.project_edit_bench(_rows(20, code_len=3000), rounds=1)
    assert big["usd"] > small["usd"] * 2
    assert small["calls"] == big["calls"]            # same call count, different spend


def test_rates_come_from_standards_and_fall_back_safely(monkeypatch):
    best, cheap = budget.rates_for("best"), budget.rates_for("cheap")
    assert best["output"] > best["input"]            # output always costs more than input
    assert best["input"] > cheap["input"]            # best tier is the expensive one
    # an unreadable standards file must not stop a run being projected
    import toolkit.standards as std
    monkeypatch.setattr(std, "load", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert budget.rates_for("best")["input"] > 0


def test_over_threshold_refuses_when_there_is_no_terminal(monkeypatch):
    # An unattended run (CI, a pipe) has nobody to answer the prompt. It must refuse, not proceed.
    monkeypatch.setattr(budget.sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.delenv("LUDWIG_ASSUME_YES", raising=False)
    p = budget.project_edit_bench(_rows(748), rounds=1)
    with pytest.raises(budget.SpendRefused):
        budget.confirm_spend(p, threshold=5.0, stream=io.StringIO())


def test_under_threshold_proceeds_without_asking(monkeypatch):
    monkeypatch.setattr(budget.sys.stdin, "isatty", lambda: False, raising=False)
    out = io.StringIO()
    budget.confirm_spend(budget.project_edit_bench(_rows(5), rounds=1),
                         threshold=5.0, stream=out)          # must not raise
    assert "proceeding" in out.getvalue()


def test_assume_yes_authorises_an_unattended_run(monkeypatch):
    monkeypatch.setattr(budget.sys.stdin, "isatty", lambda: False, raising=False)
    p = budget.project_edit_bench(_rows(748), rounds=1)
    budget.confirm_spend(p, threshold=5.0, assume_yes=True, stream=io.StringIO())
    monkeypatch.setenv("LUDWIG_ASSUME_YES", "1")
    budget.confirm_spend(p, threshold=5.0, stream=io.StringIO())


def test_a_declined_prompt_raises_and_spends_nothing(monkeypatch):
    monkeypatch.setattr(budget.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("LUDWIG_ASSUME_YES", raising=False)
    monkeypatch.setattr("builtins.input", lambda *_a: "no")
    p = budget.project_edit_bench(_rows(748), rounds=1)
    with pytest.raises(budget.SpendRefused):
        budget.confirm_spend(p, threshold=5.0, stream=io.StringIO())
    monkeypatch.setattr("builtins.input", lambda *_a: "yes")
    budget.confirm_spend(p, threshold=5.0, stream=io.StringIO())   # must not raise


def test_threshold_zero_disables_the_gate(monkeypatch):
    monkeypatch.setattr(budget.sys.stdin, "isatty", lambda: False, raising=False)
    budget.confirm_spend(budget.project_edit_bench(_rows(748), rounds=2),
                         threshold=0.0, stream=io.StringIO())      # must not raise


def test_the_projection_says_ESTIMATE_out_loud():
    # We show this to a human before they spend money; it must not read as a precise quote.
    text = budget.format_projection(budget.project_edit_bench(_rows(100), rounds=1), pace_s=6)
    assert "ESTIMATE" in text and "cannot be exact" in text
    assert "ceiling" in text and "min" in text        # call ceiling + wall time both surfaced


def test_threshold_resolves_from_ludwig_toml():
    assert budget.threshold_from_config() == 5.0      # the shipped ludwig.toml value
