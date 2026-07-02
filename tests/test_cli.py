"""CLI argv-routing tests — main() dispatch, incl. the --candidates value not leaking into the prompt.

These monkeypatch the handlers so no inference/kernel work runs: we assert only how main() routes.
"""
import cli


def _capture(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "compile_prompt",
                        lambda prompt, candidates=1: seen.setdefault("compile", (prompt, candidates)) or 0)
    monkeypatch.setattr(cli, "edit_recipe", lambda *a, **k: seen.setdefault("edit", a) or 0)
    monkeypatch.setattr(cli, "plan_recipe", lambda *a, **k: seen.setdefault("plan", (a, k)) or 0)
    return seen


def test_candidates_space_form_does_not_leak_into_prompt(monkeypatch):
    seen = _capture(monkeypatch)
    cli.main(["--candidates", "3", "a steel bracket"])
    assert seen["compile"] == ("a steel bracket", 3)   # not ("3", ...)


def test_candidates_equals_form(monkeypatch):
    seen = _capture(monkeypatch)
    cli.main(["--candidates=2", "a plate"])
    assert seen["compile"] == ("a plate", 2)


def test_bare_prompt_defaults_to_one_candidate(monkeypatch):
    seen = _capture(monkeypatch)
    cli.main(["a gusset"])
    assert seen["compile"] == ("a gusset", 1)


def test_edit_routes_to_edit_recipe(monkeypatch):
    seen = _capture(monkeypatch)
    cli.main(["--edit", "out/bracket.py", "make it 100 long"])
    assert seen["edit"][:2] == ("out/bracket.py", "make it 100 long")
    assert "compile" not in seen


def test_plan_routes_to_plan_recipe(monkeypatch):
    seen = _capture(monkeypatch)
    cli.main(["--plan", "out/bracket.py", "add an M8 hole"])
    assert seen["plan"][0][:2] == ("out/bracket.py", "add an M8 hole")
    assert "compile" not in seen
