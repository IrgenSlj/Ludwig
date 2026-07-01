"""Op-API tests (R14) — the reviewable, invertible edit spine. Pure-Python, no kernel."""
from agent.ops import (
    AddElement,
    AddFeature,
    Assemble,
    Place,
    Plan,
    SetParam,
    _substitute_all_literals,
    _substitute_unique_literal,
)

BRACKET = ('element = box("bracket", 80, 40, 6)\n'
           'clearance_hole(element, "M8", (-25, 0))\n'
           'clearance_hole(element, "M8", (25, 0))\n')


def test_plan_renders_byte_identical_to_a_hand_written_recipe():
    plan = Plan((AddElement("box", "bracket", (80, 40, 6)),
                 AddFeature("clearance_hole", ("M8", (-25, 0))),
                 AddFeature("clearance_hole", ("M8", (25, 0)))))
    assert plan.render() == BRACKET          # Ops are data that render to exactly the toolkit source


def test_op_to_source_covers_the_vocabulary():
    assert AddElement("panel", "p", (3000, 2000, 200)).to_source() == 'element = panel("p", 3000, 2000, 200)'
    assert AddFeature("anchor", (17.5, (-750, 0), 150)).to_source() == "anchor(element, 17.5, (-750, 0), 150)"
    assert Place("top", (0, 0, 10)).to_source() == "place(top, (0, 0, 10))"
    assert Assemble("asm", ("base", "top")).to_source() == 'element = assembly("asm", base, top)'


def test_setparam_apply_is_invertible():
    edited, inverse = SetParam("length", 80, 120).apply(BRACKET)
    assert 'box("bracket", 120, 40, 6)' in edited
    assert inverse == SetParam("length", 120, 80)
    restored, _ = inverse.apply(edited)
    assert restored == BRACKET               # apply → invert → original (undo)


def test_plan_apply_to_threads_setparams_and_returns_inverse():
    edited, inv = Plan((SetParam("length", 80, 120), SetParam("width", 40, 55))).apply_to(BRACKET)
    assert 'box("bracket", 120, 55, 6)' in edited
    restored, _ = inv.apply_to(edited)       # the inverse plan undoes both, in reverse order
    assert restored == BRACKET


def test_render_ignores_setparam_ops():
    # SetParam edits an existing program; it is not a line in a freshly-rendered recipe
    plan = Plan((AddElement("box", "b", (10, 10, 10)), SetParam("length", 10, 20)))
    assert plan.render() == 'element = box("b", 10, 10, 10)\n'


def test_substitution_helpers_are_importable_from_ops_post_hoist():
    # the hoist moved the editing spine into ops; the ambiguity contract is unchanged
    assert _substitute_unique_literal('box("b", 30, 30, 5)', 30, 45) is None      # ambiguous → None
    assert _substitute_all_literals('box("b", 30, 30, 5)', 30, 45) == 'box("b", 45, 45, 5)'


def test_parse_plan_validates_and_rejects_never_execs():
    # R16: the security boundary — known ops build; unknown kinds / bad shapes RAISE (never exec).
    from agent.ops import parse_plan
    good = [{"op": "AddElement", "kind": "box", "id": "bracket", "args": [80, 40, 6]},
            {"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [-25, 0]]},
            {"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [25, 0]]}]
    assert parse_plan(good).render() == BRACKET                      # JSON arrays → tuples, renders exactly
    assert parse_plan({"ops": good}).render() == BRACKET             # accepts {"ops": [...]} too

    import pytest
    with pytest.raises(ValueError):
        parse_plan([{"op": "RunShell", "cmd": "rm -rf /"}])          # unknown kind → reject
    with pytest.raises(ValueError):
        parse_plan([{"op": "AddElement", "kind": "box", "id": "b", "args": [1, 1, 1], "x": 9}])  # extra field
    with pytest.raises(ValueError):
        parse_plan([{"op": "SetParam", "name": "h"}])                # missing required old/new


def test_loop_plan_parses_a_mocked_inference_reply(monkeypatch):
    # R16: loop.plan asks the model for JSON ops and returns a validated Plan — one inference call,
    # the reply parsed as DATA (never exec'd). Mocked inference → no tokens.
    from agent import inference, loop
    reply = ('here is the plan:\n```json\n'
             '[{"op":"AddElement","kind":"box","id":"bracket","args":[80,40,6]},'
             '{"op":"AddFeature","func":"clearance_hole","args":["M8",[-25,0]]},'
             '{"op":"AddFeature","func":"clearance_hole","args":["M8",[25,0]]}]\n```')
    monkeypatch.setattr(inference, "infer", lambda *a, **k: reply)
    plan = loop.plan("an 80x40x6 bracket with two M8 holes 50 apart")
    assert plan.render() == BRACKET
