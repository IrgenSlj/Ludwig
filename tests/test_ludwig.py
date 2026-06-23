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
