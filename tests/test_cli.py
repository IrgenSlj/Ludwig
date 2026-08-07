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


# --------------------------------------------------------------------------- #
# packaging — one declaration, and CI must install THAT one
# --------------------------------------------------------------------------- #

def _pyproject():
    import tomllib
    from pathlib import Path
    return tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())


def test_requirements_txt_mirrors_pyprojects_core_dependencies():
    # Two files listing deps is exactly how CI ended up installing something the project never
    # declared. They may co-exist, but they may not disagree.
    from pathlib import Path
    import re
    proj = {re.split(r"[<>=!\[]", d)[0].strip().lower()
            for d in _pyproject()["project"]["dependencies"]}
    req = set()
    for line in (Path(__file__).parent.parent / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            req.add(re.split(r"[<>=!\[]", line)[0].strip().lower())
    assert proj == req, f"pyproject={sorted(proj)} requirements.txt={sorted(req)}"


def test_declared_packages_all_exist_and_are_importable():
    from pathlib import Path
    root = Path(__file__).parent.parent
    for pkg in _pyproject()["tool"]["setuptools"]["packages"]:
        assert (root / pkg / "__init__.py").exists(), f"{pkg} is declared but not a package"
    for mod in _pyproject()["tool"]["setuptools"]["py-modules"]:
        assert (root / f"{mod}.py").exists()
    # and nothing that is NOT a package got declared as one
    assert "tests" not in _pyproject()["tool"]["setuptools"]["packages"]


def test_ci_installs_from_pyproject_and_tests_both_ends_of_the_python_range():
    from pathlib import Path
    ci = (Path(__file__).parent.parent / ".github/workflows/ci.yml").read_text()
    assert 'pip install -e ".[' in ci, "CI must install the project's own declaration"
    # requires-python's floor must actually be in the matrix, or the floor is an unverified claim
    floor = _pyproject()["project"]["requires-python"].lstrip(">=").strip()
    assert f'"{floor}"' in ci, f"requires-python says >={floor} but CI never runs it"


def test_the_console_script_entry_point_resolves():
    import cli
    module, _, attr = _pyproject()["project"]["scripts"]["ludwig"].partition(":")
    assert module == "cli" and callable(getattr(cli, attr))
