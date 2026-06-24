"""M0 daemon wiring tests.

Monkeypatches ``ludwig.run`` so no Blender / LLM is touched — we verify that the
endpoint persists a project + run + artifacts, copies the program and render into the
project folder, and serves them back. The loop itself is covered by
``python3 ludwig.py --selftest``.

Run: ./.venv/bin/pytest tests/test_daemon.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LUDWIG_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("LUDWIG_PROJECTS", str(tmp_path / "projects"))

    import ludwig
    from daemon import app as appmod

    # minimal valid PNG bytes so copy + serve work without Blender
    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    def fake_run(brief, *, candidates, rounds, target, workers):
        assert brief
        return {
            "code": "# generated scene\nimport bpy\n",
            "critique": "FRAMING: 7\nLIGHTING: 6\nlooks reasonable",
            "score": 7.0,
            "png": str(fake_png),
            "hero": None,
        }

    monkeypatch.setattr(ludwig, "run", fake_run)
    return TestClient(appmod.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_generate_persists_and_serves(client):
    r = client.post("/api/generate", json={"brief": "a red cube", "quick": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["score"] == 7.0
    assert "code" in data["artifacts"] and "render" in data["artifacts"]
    pid = data["project_id"]

    # project detail carries the run + artifacts
    detail = client.get(f"/api/projects/{pid}")
    assert detail.status_code == 200
    proj = detail.json()
    assert proj["brief"] == "a red cube"
    run = proj["runs"][0]
    assert run["status"] == "done"
    assert run["score"] == 7.0
    kinds = {a["kind"] for a in run["artifacts"]}
    assert {"code", "render"} <= kinds

    # the program (source of truth) is downloadable and is what the loop returned
    code_id = data["artifacts"]["code"]
    f = client.get(f"/api/artifacts/{code_id}/file")
    assert f.status_code == 200
    assert b"generated scene" in f.content


def test_projects_list(client):
    client.post("/api/generate", json={"brief": "thing one", "quick": True})
    client.post("/api/generate", json={"brief": "thing two", "quick": True})
    r = client.get("/api/projects")
    assert r.status_code == 200
    briefs = {p["brief"] for p in r.json()["projects"]}
    assert {"thing one", "thing two"} <= briefs


def test_missing_project_404(client):
    assert client.get("/api/projects/does-not-exist").status_code == 404


def test_progress_parser():
    from daemon import progress

    assert progress.parse_line("=== Round 1/3  (panel of 2) ===") == {
        "type": "round", "round": 1, "rounds": 3, "candidates": 2}
    assert progress.parse_line("  • candidate foo_r1_c0.png: score 6.5") == {
        "type": "candidate", "label": "foo_r1_c0.png", "score": 6.5}
    assert progress.parse_line("  ► best so far: 7.0/10  →  /x/y.png") == {
        "type": "best", "score": 7.0, "path": "/x/y.png"}
    assert progress.parse_line("random chatter")["type"] == "log"
    assert progress.parse_line("   ") is None


def _sse_events(text):
    import json
    out = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data:"):
            out.append(json.loads(block[len("data:"):].strip()))
    return out


@pytest.fixture()
def streaming_client(monkeypatch, tmp_path):
    monkeypatch.setenv("LUDWIG_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("LUDWIG_PROJECTS", str(tmp_path / "projects"))

    import ludwig
    from daemon import app as appmod

    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    def fake_run(brief, *, candidates, rounds, target, workers):
        # emulate the real loop's stdout so the parser/stream is exercised
        print(f"=== Round 1/{rounds}  (panel of {candidates}) ===")
        print("  • candidate fake_r1_c0.png: score 7.0")
        print("  ► best so far: 7.0/10  →  " + str(fake_png))
        print(f"Winner: {fake_png}  (score 7.0/10)")
        return {"code": "# scene\nimport bpy\n", "critique": "FRAMING: 7\nok",
                "score": 7.0, "png": str(fake_png), "hero": None}

    monkeypatch.setattr(ludwig, "run", fake_run)
    return TestClient(appmod.app)


def test_generate_stream_emits_events_and_persists(streaming_client):
    r = streaming_client.post("/api/generate/stream",
                              json={"brief": "a green torus", "quick": True})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(r.text)
    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert "candidate" in types
    assert types[-1] == "done"

    done = events[-1]
    assert done["score"] == 7.0
    assert "code" in done["artifacts"] and "render" in done["artifacts"]

    # persisted and retrievable like any other run
    detail = streaming_client.get(f"/api/projects/{done['project_id']}")
    assert detail.status_code == 200
    assert detail.json()["runs"][0]["status"] == "done"
