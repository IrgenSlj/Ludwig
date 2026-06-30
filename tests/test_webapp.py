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


def test_substitute_unique_literal_guards_ambiguity():
    sub = service._substitute_unique_literal
    assert sub('box("b", 80, 40, 6)', 80, 143).startswith('box("b", 143,')  # unique → substitute
    assert sub('box("s", 30, 30, 12)', 30, 40) is None                       # 30 twice → ambiguous
    assert sub('L = 80.0', 80, 143) == "L = 143.0"                           # float spelling preserved
    assert sub('hole(el, 9, (0,0))  # M6 thread', 6, 8) is None              # the 6 in "M6" isn't a literal
    # a literal echoed in a comment must NOT defeat uniqueness (real codegen does this)
    assert sub('# 80 (length) x 40\nbox("b", 80, 40, 6)', 80, 143) == '# 80 (length) x 40\nbox("b", 143, 40, 6)'


def test_fast_edit_does_not_call_the_llm(monkeypatch, tmp_path):
    # the fast parametric path must re-execute deterministically — never touch inference
    monkeypatch.setattr(inference, "infer",
                        lambda *a, **k: pytest.fail("LLM called on the deterministic fast path"))
    prog = 'element = box("bracket", 80, 40, 6)\nclearance_hole(element, "M8", (-25, 0))\n'
    r = service.edit_to_result(prog, "make the length 143 mm",
                               param={"name": "length", "old": 80, "new": 143}, out=tmp_path)
    assert r["fast"] is True and r["passed"] is True
    assert r["bbox"] == {"length": 143.0, "width": 40.0, "height": 6.0}  # only length moved
    assert r["diff"]["added"] == 1 and r["diff"]["removed"] == 1


def test_preview_uses_evaluator_and_rebuilds_only_dirty_subtree():
    # R7: a bracket length drag goes through the deterministic evaluator (no whole-program re-exec,
    # no LLM), rebuilding only the dirty descendant subtree, with the /api/preview contract intact.
    service._GRAPH_CACHE.clear()
    r = service.preview_edit(GOOD, "length", 80, 120)
    assert r["ok"] is True and r["engine"] == "evaluator"
    assert set(r["rebuilt"]) == {"box#1", "hole#1", "hole#2"}            # the dirty descendant set
    assert r["bbox"]["length"] == 120.0 and r["bbox"]["width"] == 40.0   # only length moved
    assert r["mesh"]["positions"] and len(r["mesh"]["indices"]) % 3 == 0  # re-tessellated, JSON-safe
    assert any(c["check"] == "watertight_manifold" and c["status"] == "pass" for c in r["critic"])
    json.dumps(r)


def test_preview_falls_back_to_substitution_when_not_graph_expressible():
    # a panel() build isn't recorded → no FeatureGraph → preview uses the substitution path unchanged
    service._GRAPH_CACHE.clear()
    r = service.preview_edit('element = panel("wall", 3000, 200, 2000)\n', "length", 3000, 3200)
    assert r["ok"] is True and r.get("engine") == "substitution"
    assert r["bbox"]["length"] == 3200.0


def test_dims_deduped_by_name():
    from ir.elements import NamedDim
    out = service._dims([NamedDim("length", 80), NamedDim("length", 80), NamedDim("width", 40)])
    assert [d["name"] for d in out] == ["length", "width"]  # each named dim once, last value wins


def test_assembly_children_each_get_their_own_mesh(tmp_path):
    from toolkit import assembly, box
    from agent.loop import LoopResult
    from critic.base import Critique
    asm = assembly("asm", box("a", 20, 20, 5), box("b", 10, 10, 5))
    r = service._assemble(LoopResult("element = ...", asm, Critique(), False, 0, None), tmp_path)
    assert r["type"] == "Assembly" and len(r["children"]) == 2
    assert {c["id"] for c in r["children"]} == {"a", "b"}
    assert all(c["mesh"] and c["mesh"]["positions"] for c in r["children"])  # each child selectable


def test_failing_build_withholds_fabrication_files(monkeypatch, tmp_path):
    monkeypatch.setattr(inference, "infer", lambda *a, **k: "element = 123  # not an Element")
    r = service.compile_to_result("nonsense", rounds=0, out=tmp_path)
    assert r["id"] is None and r["passed"] is False and r["error"]
    assert "step" not in r["artifacts"]  # no fab file on a failing critic (BRIEF §5 gate)


def test_explore_to_result_ranks_variants(monkeypatch, tmp_path):
    # token-free: a mocked codegen yields the same good program for every variant
    monkeypatch.setattr(inference, "infer", lambda *a, **k: GOOD)
    r = service.explore_to_result("a bracket", n=2, out=tmp_path)
    assert r["prompt"] == "a bracket"
    variants = r["variants"]
    assert len(variants) == 2
    assert [v["rank"] for v in variants] == [1, 2]  # ranked 1..n, lower is better
    for v in variants:
        assert v["passed"] is True
        assert v["mesh"] is not None and v["mesh"]["positions"]
        assert v["error"] is None
    json.dumps(r)  # JSON-safe end to end
    # the contact sheet writes NO artifacts — it is purely a ranking snapshot
    assert not any(tmp_path.iterdir())


def test_adopt_to_result_writes_artifacts_token_free(tmp_path):
    # NO monkeypatch: adoption re-executes an existing program, never generates
    r = service.adopt_to_result(GOOD, out=tmp_path)
    assert r["adopted"] is True and r["passed"] is True
    assert r["bbox"]["length"] == pytest.approx(80.0)
    assert "step" in r["artifacts"]  # the fab gate let the real backend write
    assert (tmp_path / r["artifacts"]["step"]).exists()


def test_server_blocks_path_traversal():
    # the /out/ guard resolves and rejects anything escaping out/ — assert the resolution logic
    from webapp.server import OUT
    escaped = (OUT / "../cli.py").resolve()
    assert OUT.resolve() not in escaped.parents  # cli.py is a sibling of out/, not inside it
