"""Runtime tests — plan_stream event contract (Fix 1: skipped vs applied)."""
from agent.ops import SetParam
from agent.runtime import plan_stream

_STATE = {
    "program": 'element = box("bracket", 80, 40, 6)\n',
    "dims": {"length": 80, "width": 40, "height": 6},
}


def test_plan_stream_emits_applied_on_successful_substitution():
    # A SetParam whose old literal exists in the program → 'applied' event, state updated.
    evs = list(plan_stream("make the height 22", _STATE))
    assert [e["event"] for e in evs] == ["op", "applied", "done"]
    assert evs[-1]["state"]["program"] == 'element = box("bracket", 80, 40, 22)\n'


def test_plan_stream_emits_skipped_when_literal_not_found():
    # Fix 1: a SetParam whose old value is absent in the program must yield 'skipped', not 'applied'.
    bad_op = SetParam("length", 999, 120)   # 999 does not appear in the program
    evs = list(plan_stream("ignored", _STATE, infer=lambda i, s: [bad_op]))
    event_names = [e["event"] for e in evs]
    assert "skipped" in event_names
    assert "applied" not in event_names
    skipped = next(e for e in evs if e["event"] == "skipped")
    assert "not found" in skipped["reason"]
    assert skipped["op"]["name"] == "length"
    # state must be unchanged after a skipped op
    done = next(e for e in evs if e["event"] == "done")
    assert done["state"]["program"] == _STATE["program"]


def test_plan_stream_skipped_does_not_affect_subsequent_ops():
    # After a skipped op the stream continues; a later valid op still applies.
    bad_op = SetParam("length", 999, 120)
    good_op = SetParam("height", 6, 22)
    evs = list(plan_stream("ignored", _STATE, infer=lambda i, s: [bad_op, good_op]))
    event_names = [e["event"] for e in evs]
    assert event_names == ["op", "skipped", "op", "applied", "done"]
    assert evs[-1]["state"]["program"] == 'element = box("bracket", 80, 40, 22)\n'


def test_plan_stream_skips_colliding_edit_gracefully():
    # A colliding SetParam (new value already a distinct literal) can't be applied unambiguously by
    # all-literals substitution → its .apply raises, and the stream must degrade to 'skipped', NOT
    # 'error' (width→80 while length is already 80). Regression guard for the collision-guard layering.
    collide = SetParam("width", 40, 80)   # 80 already appears as the length literal
    evs = list(plan_stream("width 80", _STATE, infer=lambda i, s: [collide]))
    event_names = [e["event"] for e in evs]
    assert "skipped" in event_names and "error" not in event_names
    assert evs[-1]["state"]["program"] == _STATE["program"]   # unchanged
