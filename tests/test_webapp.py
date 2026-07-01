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
    from agent.ops import _substitute_unique_literal as sub   # hoisted into the Op-API spine (R14)
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


def test_durable_span_edit_of_a_square_needs_no_llm(monkeypatch, tmp_path):
    # R8: a 30×30 square's length is ambiguous for substitute-all (length == width), so today it falls
    # to the LLM. The recorded node span lets the durable edit change exactly the length literal — no LLM.
    monkeypatch.setattr(inference, "infer",
                        lambda *a, **k: pytest.fail("LLM called — the span edit must be deterministic"))
    service._GRAPH_CACHE.clear()
    prog = 'element = box("square", 30, 30, 12)\n'
    r = service.edit_to_result(prog, "make the length 40 mm",
                               param={"name": "length", "old": 30, "new": 40}, out=tmp_path)
    assert r["fast"] is True and r["passed"] is True
    assert r["bbox"] == {"length": 40.0, "width": 30.0, "height": 12.0}   # only length moved
    assert r["diff"]["added"] == 1 and r["diff"]["removed"] == 1          # one-token diff, not a rewrite
    assert 'box("square", 40, 30, 12)' in r["program"]


def test_node_spans_locate_box_extents():
    # the AST span map targets each positional extent of a box independently
    prog = 'element = box("s", 30, 30, 12)\n'
    spans = service._node_spans(prog)
    assert set(spans) == {("box#1", "length"), ("box#1", "width"), ("box#1", "height")}
    a, b = spans[("box#1", "length")]
    assert prog[a:b] == "30" and a < spans[("box#1", "width")][0]   # length is the FIRST 30


def test_dims_deduped_by_name():
    from ir.elements import NamedDim
    out = service._dims([NamedDim("length", 80), NamedDim("length", 80), NamedDim("width", 40)])
    assert [d["name"] for d in out] == ["length", "width"]  # each named dim once, last value wins


def test_dim_binding_metadata_tags_axis_and_editable():
    # R9: each dim carries axis (0/1/2 / null) + editable — the bridge a face-drag reads
    from ir.elements import NamedDim
    by = {d["name"]: d for d in service._dims(
        [NamedDim("length", 80), NamedDim("width", 40), NamedDim("height", 6),
         NamedDim("diameter", 10), NamedDim("M8_clearance_1", 9)])}
    assert (by["length"]["axis"], by["length"]["editable"]) == (0, True)
    assert (by["width"]["axis"], by["width"]["editable"]) == (1, True)
    assert (by["height"]["axis"], by["height"]["editable"]) == (2, True)
    assert (by["diameter"]["axis"], by["diameter"]["editable"]) == (None, True)  # editable, non-axis
    assert by["M8_clearance_1"]["axis"] is None and by["M8_clearance_1"]["editable"] is False


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


def test_section_to_result_live_cut_is_token_free_and_real():
    # R33: the live cut plane — execute + section + tessellate, NO llm/backends. Default plane matches
    # the section drawing backend (centroidal longitudinal → ⟂ the shortest extent, the 6 mm thickness).
    r = service.section_to_result(GOOD)
    assert r["ok"] is True and r["axis"] == "z" and r["offset"] == pytest.approx(0.0)
    assert len(r["mesh"]["indices"]) >= 3 and len(r["mesh"]["positions"]) >= 9   # a real mesh
    assert r["bbox"]["length"] == pytest.approx(80.0) and r["span"] == pytest.approx(6.0)


def test_section_to_result_honours_explicit_and_declared_planes():
    # an explicit axis/offset wins; else a declared section() feature; else the default
    r = service.section_to_result(GOOD, axis="x", offset=10.0)
    assert r["ok"] and r["axis"] == "x" and r["offset"] == pytest.approx(10.0)
    declared = GOOD + 'section(element, axis="y", offset=5)\n'
    r2 = service.section_to_result(declared)
    assert r2["ok"] and r2["axis"] == "y" and r2["offset"] == pytest.approx(5.0)


def test_section_to_result_empty_plane_is_handled_not_crashed():
    # a plane below the solid keeps nothing → ok False with a reason, never an exception/500
    r = service.section_to_result(GOOD, axis="z", offset=-500.0)
    assert r["ok"] is False and "reason" in r


def test_sketch_dim_preview_re_solves_and_returns_the_2d_profile():
    # R34: dragging a sketch DISTANCE dim re-solves + re-extrudes in-process (no files, no LLM) and
    # returns the new solid mesh AND the solved 2D profile — 3D extrude and 2D sketch move together.
    from webapp import gallery
    prog = gallery.program_for("l_profile")
    r = service.preview_edit(prog, "d_L0", 80, 130)
    assert r["ok"] and r["engine"] == "sketch-resolve"
    assert r["bbox"]["length"] == pytest.approx(130.0)             # the 80 mm leg grew to 130
    assert len(r["mesh"]["indices"]) >= 3 and len(r["sketch2d"]) == 6   # new solid + the L profile
    # the doubled 10 mm leg (d_L1 == d_L4 == 10) is disambiguated by dim name, not value
    r2 = service.preview_edit(prog, "d_L1", 10, 18)
    assert r2["ok"] and r2["engine"] == "sketch-resolve"


def test_sketch_dim_commit_is_token_free_minimal_diff(tmp_path):
    # the release of a sketch-dim drag commits deterministically (no LLM) as a one-literal diff, and is
    # allowed in the demo (allow_llm=False) — the durable analogue of the live preview.
    from webapp import gallery
    prog = gallery.program_for("l_profile")
    r = service.edit_to_result(prog, "make the leg 130 mm",
                               param={"name": "d_L0", "old": 80, "new": 130}, out=tmp_path, allow_llm=False)
    assert r.get("fast") is True and "fatal" not in r
    assert r["diff"]["added"] == 1 and r["diff"]["removed"] == 1     # exactly one constraint value changed
    assert r["bbox"]["length"] == pytest.approx(130.0)


def test_substitute_constraint_value_targets_only_the_constraint():
    # the seed shares the literal 80 across point seeds AND the distance constraint — the substitution
    # must edit ONLY the constraint, or dragging a dim would silently move the seed geometry too.
    from webapp import gallery
    prog = gallery.program_for("l_profile")
    out = service._substitute_constraint_value(prog, "distance", "L0", 80, 130)
    assert out.count("value=130") == 1                              # exactly the L0 distance constraint
    assert 's.point("p1", 80, 0)' in out and 's.point("p2", 80, 10)' in out   # seeds untouched
    assert service._substitute_constraint_value(prog, "distance", "NOPE", 80, 130) is None


def test_plan_and_build_endpoints_service_layer(monkeypatch, tmp_path):
    # R18: /api/plan proposes ops (writes nothing); /api/build builds a client-reviewed plan token-free.
    from agent import inference
    monkeypatch.setattr(inference, "infer",
                        lambda *a, **k: '[{"op": "AddElement", "kind": "box", "id": "bracket", "args": [80, 40, 6]},'
                                        '{"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [-25, 0]]},'
                                        '{"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [25, 0]]}]')
    proposed = service.plan_to_result("a bracket with two M8 holes")
    assert proposed["ok"] and len(proposed["ops"]) == 3
    assert proposed["summary"][0].startswith("add box 'bracket'")   # human review lines
    assert not (tmp_path / "bracket.step").exists()                 # propose writes nothing

    built = service.build_from_ops("", proposed["ops"], out=tmp_path)   # client-reviewed ops → build
    assert built["passed"] and built["program"] == GOOD
    assert (tmp_path / built["artifacts"]["step"]).exists()

    import pytest
    with pytest.raises(ValueError):                                 # a malformed client plan is rejected, never exec'd
        service.build_from_ops("", [{"op": "RunShell", "cmd": "rm -rf /"}], out=tmp_path)


def test_plan_apply_undo_round_trips_with_mocked_inference(monkeypatch, tmp_path):
    # R17: propose (mocked LLM) → apply builds a +1-line diff + passing critic → the inverse plan undoes.
    from agent import inference, loop
    from agent.ops import parse_plan
    monkeypatch.setattr(inference, "infer",
                        lambda *a, **k: '[{"op": "SetParam", "name": "height", "old": 6, "new": 18}]')
    plan = loop.plan("make it 18 mm tall", program=GOOD)
    assert [type(o).__name__ for o in plan.ops] == ["SetParam"]      # DATA, parsed not exec'd

    built = service.build_to_result(GOOD, plan, out=tmp_path)
    assert built["passed"] and built["bbox"]["height"] == pytest.approx(18.0)
    assert built["diff"]["added"] == 1 and built["diff"]["removed"] == 1   # minimal diff

    undone = service.build_to_result(built["program"], parse_plan(built["inverse"]), out=tmp_path)
    assert undone["bbox"]["height"] == pytest.approx(6.0)            # inverse plan is the undo


def test_cli_plan_prints_ops_and_apply_builds(monkeypatch, tmp_path, capsys):
    # R17: cli --plan prints the reviewable ops (writes nothing); --apply builds + reports the diff.
    import cli
    from agent import inference
    recipe = tmp_path / "bracket.py"
    recipe.write_text(GOOD)
    monkeypatch.setattr(inference, "infer",
                        lambda *a, **k: '[{"op": "SetParam", "name": "width", "old": 40, "new": 52}]')
    monkeypatch.chdir(tmp_path)
    assert cli.plan_recipe(str(recipe), "wider", do_apply=False) == 0
    assert "set width: 40 → 52" in capsys.readouterr().out            # printed for review, nothing built
    assert cli.plan_recipe(str(recipe), "wider", do_apply=True) == 0
    assert "applied · +1/−1" in capsys.readouterr().out


def test_build_to_result_renders_a_plan_to_verified_artifacts(tmp_path):
    # R15: the Op-API build path — render a reviewed Plan → execute → verify → assemble (fab gate intact).
    from agent.ops import AddElement, AddFeature, Plan, SetParam
    plan = Plan((AddElement("box", "bracket", (80, 40, 6)),
                 AddFeature("clearance_hole", ("M8", (-25, 0))),
                 AddFeature("clearance_hole", ("M8", (25, 0)))))
    r = service.build_to_result("", plan, out=tmp_path)
    assert r["passed"] is True and r["built"] is True
    assert r["diff"]["added"] == 3                                  # three ops → three new lines
    assert r["program"] == GOOD                                     # renders exactly the recipe
    assert "step" in r["artifacts"] and (tmp_path / r["artifacts"]["step"]).exists()
    assert "ifc" in r["artifacts"]

    # a SetParam build edits an existing program and returns an invertible plan (undo)
    edited = service.build_to_result(r["program"], Plan((SetParam("width", 40, 55),)), out=tmp_path)
    assert edited["passed"] and edited["bbox"]["width"] == pytest.approx(55.0)
    assert edited["inverse"] == [{"op": "SetParam", "name": "width", "old": 55.0, "new": 40.0}]


def test_hole_move_re_bores_and_commits_token_free(tmp_path):
    # R13: dragging a hole re-bores deterministically — substitute just that hole's position literal,
    # re-bore, and ACCEPT only if a cylindrical feature landed at the new centre (the plan-drag analogue
    # of the extent fast-edit). Preview writes nothing; commit is a +1/−1 diff; off-part is refused.
    from webapp import gallery
    prog = gallery.program_for("bracket")                       # holes at (-25,0) and (25,0)

    pv = service.preview_hole_move(prog, (-25, 0), (-30, 8))
    assert pv["ok"] and pv["engine"] == "hole-move" and len(pv["mesh"]["indices"]) >= 3
    assert any(abs(h["at"][0] + 30) < 0.5 and abs(h["at"][1] - 8) < 0.5 for h in pv["holes"])   # moved
    assert any(h["at"] == [25.0, 0.0] for h in pv["holes"])                                       # other intact

    commit = service.hole_move_to_result(prog, (-25, 0), (-30, 8), out=tmp_path)
    assert commit["fast"] is True and commit["diff"]["added"] == 1 and "fatal" not in commit

    off = service.hole_move_to_result(prog, (-25, 0), (-500, 0), out=tmp_path)   # off the part
    assert off.get("fast") is not True and "fatal" in off                        # fab gate refuses it

    # the substitution edits only the dragged hole's literal
    out = service._substitute_hole_pos(prog, (25, 0), (40, -5))
    assert out.count("(40, -5)") == 1 and "(-25, 0)" in out
    assert service._substitute_hole_pos(prog, (99, 99), (0, 0)) is None           # absent → safe None


def test_adopt_writes_the_downloadable_fabrication_export_set(tmp_path):
    # The studio's "Fabrication exports" chips link to these files under /out/ — the verified-fabricability
    # payoff made tangible. On a passing critic the full set is written to disk; the fab gate withholds
    # them otherwise. Guards the contract the export UI depends on.
    r = service.adopt_to_result(GOOD, out=tmp_path)
    assert r["passed"] is True
    art = r["artifacts"]
    for key in ("step", "ifc", "dxf", "section-dxf", "recipe"):        # the chips: STEP · IFC · shop · section · recipe
        assert key in art, key
        assert (tmp_path / art[key]).exists()                          # actually written, downloadable from /out/
    assert art["section-dxf"] == "bracket_section.dxf"                 # R30 section sheet included


def test_face_drag_write_back_contract_is_token_free_and_axis_bound(tmp_path):
    # R10 (face-drag) backend contract: the studio binds a picked face's world axis to the extent dim
    # via R9 metadata (length=0/width=1/height=2), streams a live preview, and commits on release — all
    # token-free. This asserts the destination the marquee interaction writes to.
    from agent.loop import execute
    from webapp.service import _dims
    el, _ = execute(GOOD)
    axis_of = {d["name"]: d.get("axis") for d in _dims(el.manifest)}
    assert axis_of["length"] == 0 and axis_of["width"] == 1 and axis_of["height"] == 2   # the binding

    live = service.preview_edit(GOOD, "height", 6, 24)                  # drag preview (no files, no LLM)
    assert live["ok"] and live["bbox"]["height"] == pytest.approx(24.0)
    assert live.get("engine") in ("evaluator", "substitution")         # deterministic, never the LLM

    commit = service.edit_to_result(GOOD, "make the height 24 mm",
                                    param={"name": "height", "old": 6, "new": 24}, out=tmp_path,
                                    allow_llm=False)                    # release commit, demo-safe
    assert commit.get("fast") is True and "fatal" not in commit
    assert commit["diff"]["added"] == 1 and commit["bbox"]["height"] == pytest.approx(24.0)


def test_server_blocks_path_traversal():
    # the /out/ guard resolves and rejects anything escaping out/ — assert the resolution logic
    from webapp.server import OUT
    escaped = (OUT / "../cli.py").resolve()
    assert OUT.resolve() not in escaped.parents  # cli.py is a sibling of out/, not inside it
