"""Inference seam tests — provider-blind dispatch, no real CLI invoked."""
import agent.inference as inf


def test_default_provider_is_claude(monkeypatch):
    monkeypatch.delenv("LUDWIG_PROVIDER", raising=False)
    assert inf.provider_name() == "claude"


def test_provider_switch(monkeypatch):
    monkeypatch.setenv("LUDWIG_PROVIDER", "opencode")
    assert inf.provider_name() == "opencode"


def test_run_cli_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        raise __import__("subprocess").TimeoutExpired(cmd, 1)

    monkeypatch.setattr(inf.subprocess, "run", fake_run)
    monkeypatch.setattr(inf.time, "sleep", lambda *_: None)
    try:
        inf._run_cli(["x"], timeout=1, retries=2, who="x")
        assert False, "should have raised"
    except RuntimeError:
        pass
    assert calls["n"] == 3  # initial + 2 retries
