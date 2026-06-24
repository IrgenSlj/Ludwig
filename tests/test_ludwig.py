"""Dependency-light smoke tests. Run: python3 tests/test_ludwig.py

These don't need Blender or the claude CLI — they check the pure-Python logic
(parsing, extraction) and that the generated toolkit is valid Python.
"""
import os
import py_compile
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ludwig  # noqa: E402


def test_rubric_score_averages_axes():
    text = ("FRAMING: 8\nLIGHTING: 6\nMATERIALS: 7\nBRIEF: 9\nBELIEVABILITY: 5\n"
            "KEEP: ok\nFIXES:\n- x")
    assert ludwig._score(text) == 7.0, ludwig._score(text)


def test_rubric_score_backward_compatible():
    assert ludwig._score("SCORE: 4") == 4.0


def test_rubric_score_empty_is_zero():
    assert ludwig._score("no numbers here") == 0.0


def test_extract_python_strips_fences():
    out = ludwig._extract_python("```python\nimport bpy\nx = 1\n```")
    assert out == "import bpy\nx = 1", repr(out)


def test_extract_python_finds_import():
    out = ludwig._extract_python("here you go:\nimport bpy\nx = 1")
    assert out.startswith("import bpy")


def test_find_blender_returns_str_or_none():
    assert ludwig._find_blender() is None or isinstance(ludwig._find_blender(), str)


def test_toolkit_is_valid_python():
    lib = os.path.join(os.path.dirname(ludwig.__file__), "ludwig_blender_lib.py")
    py_compile.compile(lib, doraise=True)


def test_toolkit_exposes_expected_helpers():
    assert "def L_pbr" in ludwig.BLENDER_LIB
    assert "def L_lighting" in ludwig.BLENDER_LIB
    assert "def L_autocam" in ludwig.BLENDER_LIB
    assert "def L_backdrop" in ludwig.BLENDER_LIB
    assert "def L_seat" in ludwig.BLENDER_LIB
    assert "def L_asset" in ludwig.BLENDER_LIB


def test_codegen_brief_documents_seat():
    # The model only calls helpers the brief tells it about; keep them in sync.
    assert "L_seat" in ludwig.CODEGEN_BRIEF
    assert "L_seat" in ludwig.EDIT_BRIEF


# --- render() robustness (Blender stubbed, no real render needed) ----------- #

class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _with_blender(fn):
    """Run fn with ludwig.BLENDER set so render() reaches the subprocess call."""
    saved = ludwig.BLENDER
    ludwig.BLENDER = saved or "/bin/true"
    try:
        return fn()
    finally:
        ludwig.BLENDER = saved


def test_render_timeout_is_not_fatal(tmp_path=None):
    import subprocess as sp
    out = os.path.join(os.path.dirname(__file__), "_t_timeout.png")
    orig = ludwig.subprocess.run

    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd="blender", timeout=k.get("timeout", 1))
    ludwig.subprocess.run = boom
    try:
        ok, log = _with_blender(lambda: ludwig.render("import bpy", out))
    finally:
        ludwig.subprocess.run = orig
    assert ok is False
    assert "timed out" in log


def test_render_removes_stale_png(tmp_path=None):
    """A leftover PNG must not mask a failed render that writes nothing."""
    out = os.path.join(os.path.dirname(__file__), "_t_stale.png")
    with open(out, "wb") as f:
        f.write(b"stale")
    orig = ludwig.subprocess.run
    ludwig.subprocess.run = lambda *a, **k: _FakeProc(returncode=0)  # writes no png
    try:
        ok, _ = _with_blender(lambda: ludwig.render("import bpy", out))
    finally:
        ludwig.subprocess.run = orig
    assert ok is False
    assert not os.path.exists(out)


# --- inference provider seam (no real LLM call) ----------------------------- #

def _capture_cmd(provider, **kw):
    """Run infer() under a given provider with _run_cli stubbed; return the cmd."""
    captured = {}
    orig_run, orig_env = ludwig._run_cli, os.environ.get("LUDWIG_PROVIDER")

    def _stub(cmd, **k):
        captured["cmd"] = cmd
        return "OK"
    ludwig._run_cli = _stub
    os.environ["LUDWIG_PROVIDER"] = provider
    try:
        out = ludwig.infer("PROMPT", **kw)
    finally:
        ludwig._run_cli = orig_run
        if orig_env is None:
            os.environ.pop("LUDWIG_PROVIDER", None)
        else:
            os.environ["LUDWIG_PROVIDER"] = orig_env
    return captured["cmd"], out


def test_provider_default_is_claude():
    cmd, out = _capture_cmd("claude", allow_read=True)
    assert cmd[:2] == ["claude", "-p"]
    assert "--allowedTools" in cmd and out == "OK"


def test_provider_opencode_builds_run_cmd():
    cmd, _ = _capture_cmd("opencode", image="/tmp/x.png")
    assert cmd[:2] == ["opencode", "run"]
    assert "-f" in cmd and "/tmp/x.png" in cmd       # image attached for vision
    assert cmd[-1] == "PROMPT"


def test_provider_opencode_honors_model_env():
    saved = os.environ.get("LUDWIG_MODEL")
    os.environ["LUDWIG_MODEL"] = "ollama/llama3.2-vision"
    try:
        cmd, _ = _capture_cmd("opencode")
        assert "-m" in cmd and "ollama/llama3.2-vision" in cmd
    finally:
        if saved is None:
            os.environ.pop("LUDWIG_MODEL", None)
        else:
            os.environ["LUDWIG_MODEL"] = saved


# --- agentic worker plumbing (no real agent session) ------------------------ #

def test_codegen_prompt_includes_brief_and_variant():
    p = ludwig._codegen_prompt("a teapot", variant=0)
    assert "a teapot" in p and "Interpretation A" in p


def test_agentic_off_by_default():
    assert ludwig.AGENTIC is False  # agentic is strictly opt-in (--agentic)


def test_assets_mode_injects_l_asset_instruction():
    saved = ludwig.ASSETS_MODE
    try:
        ludwig.ASSETS_MODE = False
        assert "L_asset" not in ludwig._codegen_prompt("a vase")
        ludwig.ASSETS_MODE = True
        p = ludwig._codegen_prompt("a vase")
        assert "L_asset(" in p and "if obj is None" in p  # asset call + primitive fallback
    finally:
        ludwig.ASSETS_MODE = saved


def test_agent_refine_prompt_has_done_protocol_and_fields():
    p = ludwig.AGENT_REFINE.format(brief="a vase", png="/r/x.png", code="import bpy")
    assert "DONE" in p and "a vase" in p and "/r/x.png" in p and "import bpy" in p


def test_agentic_build_loops_and_self_corrects(tmp_path=None):
    """Drive _agentic_build with infer()/render() stubbed: it should re-render
    improved code until the model replies DONE, returning the last good build."""
    out = os.path.join(os.path.dirname(__file__), "_t_agent.png")
    calls = {"infer": 0, "render": 0}
    orig_infer, orig_render, orig_oneshot = (
        ludwig.infer, ludwig.render, ludwig._oneshot_build)
    ludwig._oneshot_build = lambda *a, **k: ("CODE_v0", True, "log0")
    # first refine returns improved code, second says DONE
    responses = ["import bpy  # CODE_v1", "DONE"]
    def fake_infer(prompt, **k):
        calls["infer"] += 1
        return responses[calls["infer"] - 1]
    def fake_render(code, png, **k):
        calls["render"] += 1
        with open(png, "w") as fh:        # real render() guarantees the file exists on ok
            fh.write("x")
        return True, "ok"
    ludwig.infer, ludwig.render = fake_infer, fake_render
    saved_turns = ludwig.AGENT_TURNS
    ludwig.AGENT_TURNS = 3
    try:
        code, ok, _ = ludwig._agentic_build("a vase", out, variant=0)
    finally:
        (ludwig.infer, ludwig.render, ludwig._oneshot_build, ludwig.AGENT_TURNS) = (
            orig_infer, orig_render, orig_oneshot, saved_turns)
        for p in (out, out.replace(".png", "_try.png")):
            if os.path.exists(p):
                os.remove(p)
    assert ok and code == "import bpy  # CODE_v1"   # adopted v1, stopped on DONE
    assert calls["infer"] == 2 and calls["render"] == 1


# --- eval harness pure logic (no LLM/Blender) ------------------------------- #

def test_axis_scores_parses_all_axes():
    text = ("FRAMING: 7\nLIGHTING: 5.5\nMATERIALS: 6\nBRIEF: 8\n"
            "BELIEVABILITY: 4\nKEEP: x")
    ax = ludwig._axis_scores(text)
    assert ax == {"FRAMING": 7.0, "LIGHTING": 5.5, "MATERIALS": 6.0,
                  "BRIEF": 8.0, "BELIEVABILITY": 4.0}


def test_axis_scores_empty_is_empty():
    assert ludwig._axis_scores("no numbers") == {}


def test_latest_record_returns_last_matching_mode(tmp_path=None):
    import json as _json
    f = os.path.join(os.path.dirname(__file__), "_t_results.jsonl")
    rows = [{"mode": "oneshot", "mean": 4.0}, {"mode": "agentic", "mean": 5.0},
            {"mode": "oneshot", "mean": 4.6}]
    with open(f, "w") as fh:
        for r in rows:
            fh.write(_json.dumps(r) + "\n")
    saved = ludwig.EVAL_RESULTS
    ludwig.EVAL_RESULTS = f
    try:
        assert ludwig._latest_record("oneshot")["mean"] == 4.6   # last oneshot
        assert ludwig._latest_record("agentic")["mean"] == 5.0
        assert ludwig._latest_record("nope") is None
    finally:
        ludwig.EVAL_RESULTS = saved
        os.remove(f)


def test_eval_brief_suite_is_fixed_and_nonempty():
    # The suite must stay stable for runs to be comparable over time.
    assert len(ludwig.EVAL_BRIEFS) >= 4
    assert all(isinstance(b, str) and b for b in ludwig.EVAL_BRIEFS)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
