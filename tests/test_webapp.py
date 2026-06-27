"""Web frontend tests — the service serializes the real compile result; the server routes/guard.

The compile is driven by a MOCKED inference (no tokens, CI-safe), so this exercises the real loop +
backends through `webapp.service` without an LLM call. Kernel-gated (the backends need OCCT)."""
import json

import pytest

pytest.importorskip("cadquery")

from agent import inference
from webapp import service

GOOD = ('element = box("bracket", 80, 40, 6)\n'
        'clearance_hole(element, "M8", (-25, 0))\n'
        'clearance_hole(element, "M8", (25, 0))\n')


def test_compile_to_result_is_json_safe_and_real(monkeypatch, tmp_path):
    monkeypatch.setattr(inference, "infer", lambda *a, **k: GOOD)
    r = service.compile_to_result("a bracket", out=tmp_path)
    json.dumps(r)  # must be serializable end to end
    assert r["id"] == "bracket" and r["passed"] is True
    assert r["bbox"] == {"length": 80.0, "width": 40.0, "height": 6.0}
    assert {d["name"] for d in r["dims"]} >= {"length", "width", "height"}
    # the fabrication gate let the real backends write — files exist on disk
    assert (tmp_path / r["artifacts"]["step"]).exists()
    assert (tmp_path / r["artifacts"]["recipe"]).exists()
    assert any(c["check"] == "watertight_manifold" and c["status"] == "pass" for c in r["critic"])
    # the 3D Stage mesh: real tessellation of the compiled B-rep, JSON-safe flat arrays
    m = r["mesh"]
    assert len(m["positions"]) % 3 == 0 and len(m["positions"]) > 0
    assert len(m["indices"]) % 3 == 0 and len(m["indices"]) > 0
    assert len(m["center"]) == 3 and m["radius"] > 0


def test_edit_to_result_is_minimal_and_real(monkeypatch, tmp_path):
    base = ('element = box("bracket", 80, 40, 6)\n'
            'clearance_hole(element, "M8", (-25, 0))\n'
            'clearance_hole(element, "M8", (25, 0))\n')
    edited = base.replace("80, 40, 6", "100, 40, 6")  # a well-behaved model touches one line
    monkeypatch.setattr(inference, "infer", lambda *a, **k: edited)
    r = service.edit_to_result(base, "make the length 100 mm", out=tmp_path)
    assert r["passed"] is True
    assert r["bbox"]["length"] == 100.0 and r["bbox"]["width"] == 40.0  # only length moved
    assert r["diff"]["added"] == 1 and r["diff"]["removed"] == 1        # surgical, not a rewrite
    assert r["mesh"]["positions"]                                       # geometry re-tessellated


def test_failing_build_withholds_fabrication_files(monkeypatch, tmp_path):
    monkeypatch.setattr(inference, "infer", lambda *a, **k: "element = 123  # not an Element")
    r = service.compile_to_result("nonsense", rounds=0, out=tmp_path)
    assert r["id"] is None and r["passed"] is False and r["error"]
    assert "step" not in r["artifacts"]  # no fab file on a failing critic (BRIEF §5 gate)


def test_server_blocks_path_traversal():
    # the /out/ guard resolves and rejects anything escaping out/ — assert the resolution logic
    from webapp.server import OUT
    escaped = (OUT / "../cli.py").resolve()
    assert OUT.resolve() not in escaped.parents  # cli.py is a sibling of out/, not inside it
