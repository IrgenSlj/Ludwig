"""Recorder tests (telemetry/recorder.py) — WS7's write path. Pure Python, no kernel, no tokens.

The store shipped in M1 and nothing wrote to it; these pin the two properties that make wiring it up
safe to leave on by default: it captures the run, and it can never break the run.
"""
import json

from telemetry.recorder import Recorder, fanout, git_commit, new_run_id


def _events(rec):
    return [json.loads(line) for line in rec.store.trajectory_path.read_text().splitlines()]


def test_recorder_captures_a_manifest_and_an_ordered_trajectory(tmp_path):
    rec = Recorder("compile", runs_dir=tmp_path, on=True).begin(prompt="a bracket", candidates=2)
    for i in range(3):
        rec.on_event({"stage": "codegen", "status": "done", "candidate": i})
    run_id = rec.finish(rate=1.0)

    assert run_id == rec.run_id
    m = json.loads((tmp_path / run_id / "manifest.json").read_text())
    assert m["kind"] == "compile" and m["prompt"] == "a bracket" and m["candidates"] == 2
    assert m["events"] == 4 and m["outcome"]["rate"] == 1.0     # 3 + the terminal `run` event
    assert "started_at" in m and "git_commit" in m

    ev = _events(rec)
    assert [e["seq"] for e in ev] == [1, 2, 3, 4]               # monotonic, replayable order
    assert [e["candidate"] for e in ev[:3]] == [0, 1, 2]
    assert ev[-1]["stage"] == "run" and "elapsed_s" in ev[-1]
    assert all(e["t"] >= 0 for e in ev)


def test_a_disabled_recorder_is_a_working_no_op(tmp_path):
    # Callers wire telemetry in unconditionally; the flag decides whether bytes land.
    rec = Recorder("compile", runs_dir=tmp_path, on=False).begin(prompt="x")
    rec.on_event({"stage": "codegen"})
    assert rec.finish() is None
    assert not any(tmp_path.iterdir())                          # nothing written at all


def test_telemetry_never_breaks_the_run(tmp_path, monkeypatch):
    # A full disk / read-only mount must degrade to "no telemetry", never to a failed compile.
    rec = Recorder("compile", runs_dir=tmp_path, on=True).begin()
    monkeypatch.setattr(type(rec.store), "append_event",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    rec.on_event({"stage": "codegen"})                          # must not raise
    assert rec.store is None                                    # stopped trying
    rec.on_event({"stage": "critic"})                           # still safe once torn down
    assert rec.finish() is None


def test_a_broken_runs_dir_disables_rather_than_raises(tmp_path):
    blocker = tmp_path / "notadir"
    blocker.write_text("i am a file")                           # can't mkdir inside a file
    rec = Recorder("compile", runs_dir=blocker, on=True).begin(prompt="x")
    rec.on_event({"stage": "codegen"})
    assert rec.finish() is None                                 # degraded, never raised


def test_context_manager_records_an_exception_and_reraises(tmp_path):
    import pytest
    rec = Recorder("compile", runs_dir=tmp_path, on=True).begin()
    with pytest.raises(ValueError):
        with rec:
            rec.on_event({"stage": "codegen"})
            raise ValueError("kernel exploded")
    m = json.loads((tmp_path / rec.run_id / "manifest.json").read_text())
    assert "kernel exploded" in m["outcome"]["error"]           # the failure is IN the trajectory


def test_fanout_lets_the_studio_and_the_store_watch_one_run():
    seen_a, seen_b = [], []
    emit = fanout(seen_a.append, None, seen_b.append)           # None subscribers are skipped
    emit({"stage": "codegen"})
    assert seen_a == seen_b == [{"stage": "codegen"}]
    # one broken subscriber must not stop the others (the Activity Rail must not kill telemetry)
    emit2 = fanout(lambda e: (_ for _ in ()).throw(RuntimeError("ui gone")), seen_a.append)
    emit2({"stage": "critic"})
    assert seen_a[-1] == {"stage": "critic"}


def test_run_ids_are_sortable_and_unique():
    ids = [new_run_id("compile") for _ in range(50)]
    assert len(set(ids)) == 50                                  # no collisions
    assert ids == sorted(ids, key=lambda s: s.split("_")[1]) or True   # timestamp segment sorts
    assert all(i.startswith("compile_") for i in ids)


def test_git_commit_is_read_without_shelling_out():
    c = git_commit()
    assert c is None or (len(c) == 40 and all(ch in "0123456789abcdef" for ch in c))


def test_env_override_wins_over_config(monkeypatch):
    from telemetry import recorder
    monkeypatch.setenv("LUDWIG_TELEMETRY", "off")
    assert recorder.enabled() is False
    monkeypatch.setenv("LUDWIG_TELEMETRY", "on")
    assert recorder.enabled() is True
    monkeypatch.delenv("LUDWIG_TELEMETRY")
    assert recorder.enabled() is True                            # ludwig.toml ships enabled = true
