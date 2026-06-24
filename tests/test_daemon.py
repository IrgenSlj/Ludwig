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
