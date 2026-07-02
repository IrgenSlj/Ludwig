"""Streaming agent runtime (R23) — a generator that turns an instruction into a stream of reviewable
op events, one at a time, so the studio can paint a live agent lane.

The seam is INJECTABLE and TOKEN-FREE by default: `infer` parses the instruction into Ops, and its
default is a deterministic local grammar (`"going 320"` → `SetParam('going', …, 320)`) that costs zero
tokens — the LLM planner (R26) is the same seam with `infer=inference.infer`. `apply` folds each op into
the running state (program + dims). The generator yields `op` (proposed), `applied`, `done`, `error`,
and `cancelled` events, and honours `should_cancel()` between ops (R25's Stop). Pure-Python, no kernel.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Callable, Optional

from agent.ops import SetParam, summarize


def _op_json(op) -> dict:
    return {"op": type(op).__name__, **asdict(op)}


def local_grammar(instruction: str, state: dict) -> list:
    """Zero-token parse of a simple parametric instruction into SetParam ops. Recognises
    `<known-dim> … <number>` (e.g. 'going 320', 'make the height 24 mm') for any dim in the state, and
    only emits an op when the value actually changes. Unrecognised → [] (the caller streams nothing)."""
    dims = state.get("dims", {})
    text = instruction.lower()
    ops = []
    for name, old in dims.items():
        m = re.search(rf"\b{re.escape(name.lower())}\b[^\d-]{{0,14}}(-?\d+(?:\.\d+)?)", text)
        if m and abs(float(m.group(1)) - float(old)) > 1e-9:
            ops.append(SetParam(name, float(old), float(m.group(1))))
    return ops


def _default_apply(op, state: dict) -> dict:
    """Fold one op into the running state (program text + dim map). Deterministic, token-free. A SetParam
    rewrites its literal; any other op (AddElement/AddFeature/…) appends its rendered source as a build
    step — the same source the Op-API renders, never model-authored code."""
    program = state.get("program", "")
    if isinstance(op, SetParam):
        new_program, _inv = op.apply(program)
        if new_program is None:
            return state
        return {**state, "program": new_program, "dims": {**state.get("dims", {}), op.name: op.new}}
    src = op.to_source()
    joiner = "\n" if program and not program.endswith("\n") else ""
    return {**state, "program": program + joiner + src + "\n"}


def plan_stream(instruction: str, state: dict, *,
                infer: Optional[Callable] = None,
                apply: Optional[Callable] = None,
                should_cancel: Optional[Callable] = None,
                on_event: Optional[Callable] = None):
    """Stream an instruction as a sequence of op events. Yields (and mirrors to `on_event`) dicts:
    `{event: 'op'|'applied'|'done'|'error'|'cancelled', …}`. `infer(instruction, state) -> [Op]` and
    `apply(op, state) -> state` are injectable (defaults: the local grammar + set_param fold — no LLM).
    `should_cancel()` is polled before each op so a Stop halts cleanly (R25)."""
    infer = infer or local_grammar
    apply = apply or _default_apply
    should_cancel = should_cancel or (lambda: False)

    def emit(ev: dict) -> dict:
        if on_event:
            on_event(ev)
        return ev

    try:
        if should_cancel():
            yield emit({"event": "cancelled"})
            return
        ops = infer(instruction, state)
        for op in ops:
            if should_cancel():
                yield emit({"event": "cancelled"})
                return
            yield emit({"event": "op", "op": _op_json(op), "summary": summarize(op)})
            state = apply(op, state)
            yield emit({"event": "applied", "op": _op_json(op)})
        yield emit({"event": "done", "state": {"program": state.get("program", ""),
                                               "dims": state.get("dims", {})}, "count": len(ops)})
    except Exception as e:  # pragma: no cover - defensive; a bad op never crashes the stream
        yield emit({"event": "error", "message": f"{type(e).__name__}: {e}"})


def llm_infer(instruction: str, state: dict, *, infer_fn: Optional[Callable] = None,
              model: Optional[str] = None) -> list:
    """LLM planner for the stream (R26): ONE cheap-tier inference call → JSON ops → strict-validated Op
    list, consuming the same Op-API schema as the CLI/webapp. A malformed reply (bad JSON, unknown op,
    wrong shape) yields NO ops — nothing model-authored is ever exec'd; the caller streams an error chip.
    `infer_fn` is injectable so the gate can drive it with canned JSON (token-free)."""
    from agent.loop import _plan_prompt, _tier_model
    from agent.ops import extract_json, parse_plan

    if infer_fn is None:
        from agent import inference
        infer_fn = inference.infer
    reply = infer_fn(_plan_prompt(instruction, state.get("program", ""), None),
                     model=model or _tier_model("codegen"))   # planning ops is cheap-tier work
    try:
        return list(parse_plan(extract_json(reply)).ops)
    except (ValueError, TypeError):
        return []   # malformed / unknown op → drop the whole plan; never exec model text


def hybrid_infer(instruction: str, state: dict, *, infer_fn: Optional[Callable] = None,
                 model: Optional[str] = None) -> list:
    """The local-mode planner: the free, instant local grammar for a plain '<dim> <number>' edit, else
    the LLM (R26). Keeps the common parametric tweak token-free and reserves inference for real language."""
    ops = local_grammar(instruction, state)
    return ops if ops else llm_infer(instruction, state, infer_fn=infer_fn, model=model)


__all__ = ["plan_stream", "local_grammar", "llm_infer", "hybrid_infer"]
