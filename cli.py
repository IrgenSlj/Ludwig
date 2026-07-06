#!/usr/bin/env python3
"""Ludwig CLI — the headless entry point (BRIEF §7).

  python3 cli.py "a steel bracket, 80x40x6mm, two M8 holes"   # P0/S3+ — compile a model
  python3 cli.py --edit <path> "make the holes M10"           # P0/S6 — minimal-diff re-prompt
  python3 cli.py --selftest                                   # the regression gate (no LLM tokens)

--selftest is the gate that stays green at every phase. Today it exercises the pure-Python IR
spine (no kernel, no inference); it grows a real OCCT build once the geometry service lands (S2/S5).
"""
from __future__ import annotations

import os
import sys


def selftest() -> int:
    """Pure-Python invariants of the IR spine. Grows into a real OCCT build at S2/S5."""
    from ir import Element, NamedDim, Param, ProgramNode
    from toolkit import box

    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, bool(ok), detail))

    # Units are mandatory (the #1 silent CAD bug).
    try:
        Param("width", 80, unit="")
        check("param requires unit", False, "no-unit Param was accepted")
    except ValueError:
        check("param requires unit", True)

    # Inference throttle-detection (A4): a rate/usage-limit stderr triggers the longer backoff so a
    # transient limit self-heals instead of surfacing as an empty program (the eval throttling artifact).
    from agent.inference import _THROTTLE_RE
    check("throttle-detect: rate-limit signatures match",
          all(_THROTTLE_RE.search(s) for s in ("429 Too Many Requests", "usage limit reached",
                                               "overloaded_error", "please try again later")))
    check("throttle-detect: a normal error does NOT match",
          not _THROTTLE_RE.search("SyntaxError: invalid syntax on line 3"))

    # Repair corpus (A5) — off by default (measure-don't-assert), and a record→retrieve round-trip
    # keys on the normalized failure signature. Pure-Python; the loop is untouched when the corpus is off.
    from pathlib import Path
    from store import repairs as _rc
    check("repair corpus: OFF by default (unmeasured → default off)", _rc.enabled() is False)
    check("repair corpus: signature folds sub-checks to base names",
          _rc.signature_of([{"check": "min_wall"}, {"check": "cover:anchor_1"}]) == "cover min_wall")
    _c = _rc.connect(Path(__file__).resolve().parent / "store" / "_selftest.sqlite")
    _c.execute("DELETE FROM repair")
    _rc.record(_c, broken="hole(e,(35,0))", fixed="hole(e,(28,0))", source="pool_x",
               failures=[{"check": "min_wall", "message": "0.5 < 1.5"}])
    _hit = _rc.retrieve(_c, [{"check": "min_wall"}])
    check("repair corpus: retrieval keys on failure signature + renders a diff",
          bool(_hit) and _hit[0]["signature"] == "min_wall" and _rc.as_prompt(_hit).strip() != "")
    check("repair corpus: exclude_source guards against leakage",
          _rc.retrieve(_c, [{"check": "min_wall"}], exclude_source="pool_x") == [])
    _c.close()
    (Path(__file__).resolve().parent / "store" / "_selftest.sqlite").unlink(missing_ok=True)

    # crystallization clamps to [0,1] and is a scalar only ([H3]).
    e = Element(id="x", crystallization=2.5)
    check("crystallization clamps", e.crystallization == 1.0, f"got {e.crystallization}")

    # The bracket IR assembles without touching the kernel (lazy geometry).
    b = box("bracket", 80, 40, 6, name="steel bracket")
    check("bbox dims registered", b.dim("length") == 80 and b.dim("width") == 40 and b.dim("height") == 6)
    check("geometry is lazy", b.geometry is not None and not b.geometry.built)
    check("named dims feed manifest", all(isinstance(d, NamedDim) for d in b.manifest))

    # Provenance resolves to a program node, never a kernel handle ([H2]).
    b.provenance = ProgramNode(node_id="bracket", source_span=(1, 12))
    check("provenance is a ProgramNode", isinstance(b.provenance, ProgramNode))

    # Feature graph recorder — R2 gate (pure-Python, kernel-free).
    # Builds the bracket recipe under recording() and asserts stable node ids + correct params.
    from toolkit.elements import recording as _recording
    from toolkit import clearance_hole as _clearance_hole

    def _build_bracket_graph():
        with _recording() as _g:
            _b = box("_bracket_r2", 80, 40, 6)
            _clearance_hole(_b, "M8", (-25, 0))
            _clearance_hole(_b, "M8", (25, 0))
        return _g

    _g1 = _build_bracket_graph()
    _g2 = _build_bracket_graph()

    check("feature graph: 3 nodes (box + 2 clearance holes)",
          len(_g1.nodes) == 3,
          f"got {len(_g1.nodes)}: {[n.node_id for n in _g1.nodes]}")
    check("feature graph: ids box#1 / hole#1 / hole#2",
          [n.node_id for n in _g1.nodes] == ["box#1", "hole#1", "hole#2"],
          f"got {[n.node_id for n in _g1.nodes]}")
    check("feature graph: box params 80x40x6 mm",
          _g1.nodes[0].params.get("length") == 80
          and _g1.nodes[0].params.get("width") == 40
          and _g1.nodes[0].params.get("height") == 6,
          f"box params={_g1.nodes[0].params}")
    check("feature graph: M8 clearance holes -> dia 9.0 mm",
          _g1.nodes[1].params.get("diameter") == 9.0
          and _g1.nodes[2].params.get("diameter") == 9.0,
          f"diameters={_g1.nodes[1].params.get('diameter')}, {_g1.nodes[2].params.get('diameter')}")
    check("feature graph: ids lineage-stable across independent builds",
          [n.node_id for n in _g1.nodes] == [n.node_id for n in _g2.nodes],
          f"run1={[n.node_id for n in _g1.nodes]} run2={[n.node_id for n in _g2.nodes]}")
    check("feature graph: recording OFF by default (unrecorded box has graph=None)",
          box("_no_record", 10, 10, 10).graph is None)

    # R27 — sketch constraint solver (pure-Python, no kernel). A fully-constrained rectangle solves to
    # exact corners; dropping the two distance dims leaves exactly 2 DoF — reported deterministically.
    from geometry.sketch_solver import solve as _solve_sketch
    from ir.sketch import Sketch

    def _rect(dims: bool = True):
        s = Sketch("r")
        s.point("a", 0, 0, fixed=True)                                  # anchor removes translation DoF
        s.point("b", 35, 3); s.point("c", 33, 18); s.point("d", 2, 19)  # rough initial corners
        for lid, p, q in [("L0", "a", "b"), ("L1", "b", "c"), ("L2", "c", "d"), ("L3", "d", "a")]:
            s.line(lid, p, q)
        s.constrain("horizontal", "L0"); s.constrain("vertical", "L1")
        s.constrain("horizontal", "L2"); s.constrain("vertical", "L3")
        if dims:
            s.constrain("distance", "L0", value=40); s.constrain("distance", "L1", value=20)
        return s

    _rs = _solve_sketch(_rect(True))
    _want = {"a": (0, 0), "b": (40, 0), "c": (40, 20), "d": (0, 20)}
    _corners_ok = all(abs(_rs.coords[k][i] - _want[k][i]) < 1e-6 for k in _want for i in (0, 1))
    check("sketch: constrained rectangle solves to exact corners (1e-6)",
          _rs.solved and _rs.dof == 0 and _corners_ok,
          f"solved={_rs.solved} dof={_rs.dof} resid={_rs.residual_norm:.1e}")
    check("sketch: under-constrained rectangle reports 2 remaining DoF",
          _solve_sketch(_rect(False)).dof == 2, f"dof={_solve_sketch(_rect(False)).dof}")

    # R32 — sketch DoF critic in the deterministic panel. The solver's DoF/redundancy feeds a critic
    # that WARNs on under-constrained and ERRORs on conflicting/over-constrained — added via
    # critic.panel.register with NO agent/loop.py change ([H4]).
    from types import SimpleNamespace as _NS

    from critic import sketch as _sk_critic
    from critic.panel import critics as _critics

    def _feat(res):    # exactly what toolkit.extrude records on the element
        return {"kind": "sketch", "dof": int(res.dof), "solved": bool(res.solved),
                "residual": float(res.residual_norm), "redundant": int(res.redundant)}

    _full = _sk_critic.evaluate(_NS(id="r", features=[_feat(_solve_sketch(_rect(True)))]), None).checks[0]
    check("R32: a fully-constrained sketch PASSES the DoF critic",
          _full.status.value == "pass", f"{_full.status.value} · {_full.message}")

    def _conflict():   # two different lengths on one line → unsatisfiable
        s = Sketch("x"); s.point("a", 0, 0, fixed=True); s.point("b", 40, 0); s.line("L0", "a", "b")
        s.constrain("distance", "L0", value=40); s.constrain("distance", "L0", value=55)
        return s

    _bad = _sk_critic.evaluate(_NS(id="x", features=[_feat(_solve_sketch(_conflict()))]), None).checks[0]
    check("R32: a conflicting (over-constrained) sketch FAILS as ERROR",
          _bad.status.value == "fail" and _bad.severity.name == "ERROR" and "conflict" in _bad.message.lower(),
          f"{_bad.status.value}/{_bad.severity.name} · {_bad.message}")
    check("R32: the sketch critic is registered in the panel (no loop change)",
          any(getattr(c, "name", "") == "sketch" for c in _critics()))

    # R14 — Op vocabulary: a plan of typed Ops (DATA, never exec'd) renders to source byte-identical to a
    # hand-written recipe, and a SetParam edit is invertible (undo) — the reviewable edit spine for the Op-API.
    from agent.ops import AddElement, AddFeature, Plan, SetParam
    _bp = Plan((AddElement("box", "bracket", (80, 40, 6)),
                AddFeature("clearance_hole", ("M8", (-25, 0))),
                AddFeature("clearance_hole", ("M8", (25, 0)))))
    _expected = ('element = box("bracket", 80, 40, 6)\n'
                 'clearance_hole(element, "M8", (-25, 0))\n'
                 'clearance_hole(element, "M8", (25, 0))\n')
    check("R14: a 3-op plan renders byte-identical to the bracket recipe",
          _bp.render() == _expected, repr(_bp.render()[:38]))
    _edited, _inv = Plan((SetParam("length", 80, 120),)).apply_to(_expected)
    _restored, _ = _inv.apply_to(_edited)
    check("R14: a SetParam edit applies then inverts back to the original (undo)",
          "120" in _edited and _restored == _expected,
          f"has-120={'120' in _edited} restored-ok={_restored == _expected}")

    # R16 — the planner emits JSON ops (DATA, never exec'd): parse_plan strict-validates a bracket plan to
    # a Plan that renders byte-identical, and REJECTS an unknown op kind / unexpected field — the security
    # boundary that replaces exec'ing model-authored Python.
    from agent.ops import parse_plan as _parse
    _json_plan = [{"op": "AddElement", "kind": "box", "id": "bracket", "args": [80, 40, 6]},
                  {"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [-25, 0]]},
                  {"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [25, 0]]}]
    check("R16: a JSON op-plan parses + renders byte-identical to the bracket recipe",
          _parse(_json_plan).render() == _expected, repr(_parse(_json_plan).render()[:38]))

    def _raises(fn):
        try:
            fn()
            return False
        except (ValueError, TypeError):
            return True

    check("R16: parse_plan rejects an unknown op kind AND an unexpected field (nothing exec'd)",
          _raises(lambda: _parse([{"op": "RunShell", "cmd": "rm -rf /"}]))
          and _raises(lambda: _parse([{"op": "AddElement", "kind": "box", "id": "b",
                                       "args": [1, 1, 1], "evil": 1}]))
          and _raises(lambda: _parse([{"op": "AddElement", "kind": "box"}])),   # missing required id/args
          "strict validation")

    # R17 — reviewable edits: each op reads as a one-line summary for `cli --plan` before `--apply`.
    from agent.ops import summarize as _summ
    _ops = _parse(_json_plan).ops
    check("R17: op plans summarize for review (--plan prints, --apply builds)",
          _summ(_ops[0]).startswith("add box 'bracket'") and "add clearance_hole" in _summ(_ops[1]),
          f"{_summ(_ops[0])} | {_summ(_ops[1])}")

    # R23 — streaming agent runtime: a token-free local grammar turns an instruction into a stream of op
    # events (op → applied → done), zero LLM; should_cancel halts cleanly. The injectable seam the LLM
    # planner (R26) plugs into with infer=inference.infer.
    from agent.runtime import plan_stream as _pstream
    _st = {"program": 'element = stair("s", rise=170, going=280, width=1000, riser_count=17)\n',
           "dims": {"rise": 170, "going": 280, "width": 1000, "riser_count": 17}}
    _evs = list(_pstream("going 320", _st))
    check("R23: plan_stream streams 'going 320' → op → applied → done (deterministic, token-free)",
          [e["event"] for e in _evs] == ["op", "applied", "done"]
          and _evs[0]["op"]["op"] == "SetParam" and _evs[0]["op"]["new"] == 320.0
          and _evs[-1]["state"]["dims"]["going"] == 320.0,
          f"{[e['event'] for e in _evs]}")
    check("R23: plan_stream honours should_cancel (Stop) — zero ops, one 'cancelled'",
          [e["event"] for e in _pstream("going 320", _st, should_cancel=lambda: True)] == ["cancelled"])

    # R26 — LLM op-planner behind the SAME stream seam: a canned JSON reply parses to validated ops
    # (consuming the Op-API schema, never exec'd); a malformed or unknown-op reply yields none; the
    # hybrid keeps a plain '<dim> <number>' edit on the free grammar (no inference call). Token-free gate.
    from agent.runtime import hybrid_infer as _hyb
    from agent.runtime import llm_infer as _llm
    _canned = '```json\n[{"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [0, 0]]}]\n```'
    _ops26 = _llm("add a hole", {"program": 'element = box("b", 80, 40, 6)\n'},
                  infer_fn=lambda *a, **k: _canned)
    check("R26: LLM infer parses a canned JSON reply into validated ops (token-free, never exec'd)",
          len(_ops26) == 1 and type(_ops26[0]).__name__ == "AddFeature", f"{[type(o).__name__ for o in _ops26]}")
    check("R26: a malformed or unknown-op reply yields NO ops (rejected, never exec'd)",
          _llm("x", {"program": ""}, infer_fn=lambda *a, **k: "not json") == []
          and _llm("x", {"program": ""}, infer_fn=lambda *a, **k: '[{"op":"RunShell","cmd":"rm -rf /"}]') == [])
    _called = []
    _hops = _hyb("height 20", {"dims": {"height": 6}, "program": 'element = box("b", 80, 40, 6)\n'},
                 infer_fn=lambda *a, **k: (_called.append(1), "[]")[1])
    check("R26: hybrid keeps a plain '<dim> <number>' edit on the free grammar (no inference call)",
          len(_hops) == 1 and type(_hops[0]).__name__ == "SetParam" and not _called)

    # A1 — the wire contract carries a version. stamp() adds SCHEMA_VERSION when absent and NEVER
    # overwrites one already set (a nested builder's version wins), so every client can read the shape.
    from webapp import service as _svc
    check("A1: schema_version stamped onto payloads, idempotently (the wire contract version)",
          isinstance(_svc.SCHEMA_VERSION, str) and _svc.SCHEMA_VERSION
          and _svc.stamp({"a": 1})["schema_version"] == _svc.SCHEMA_VERSION
          and _svc.stamp({"schema_version": "9.9"})["schema_version"] == "9.9",
          f"version={_svc.SCHEMA_VERSION!r}")

    # D1 — the loopback-auth boundary the embedding shell relies on. No token → open (back-compat);
    # a token → an exact, constant-time match is required, and a missing/wrong one is rejected.
    from webapp.server import token_ok as _tok
    check("D1: token_ok is open with no token, strict with one (the daemon auth boundary)",
          _tok(None, None) is True and _tok(None, "anything") is True
          and _tok("s3cret", "s3cret") is True
          and _tok("s3cret", "wrong") is False and _tok("s3cret", None) is False
          and _tok("s3cret", "") is False,
          "loopback token gate")

    # A2 — the MCP server module imports WITHOUT the SDK (the SDK is lazy, inside build_server), so the
    # spine stays green on a machine that never runs `ludwig mcp`. If the SDK IS present, the v1 tool
    # surface (compile/verify/export) registers.
    import agent.mcp as _mcp
    _mcp_ok = callable(_mcp.build_server) and callable(_mcp.main)
    try:
        import asyncio as _aio

        import mcp as _mcp_sdk  # noqa: F401
        _tools = {t.name for t in _aio.run(_mcp.build_server().list_tools())}
        _mcp_ok = _mcp_ok and {"ludwig_compile", "ludwig_verify", "ludwig_export"} <= _tools
        _detail = f"tools={sorted(_tools)}"
    except ImportError:
        _detail = "SDK absent — module import checked (lazy SDK)"
    check("A2: MCP server imports SDK-free; registers compile/verify/export when the SDK is present",
          _mcp_ok, _detail)

    # A3 — the permission gate. Headless-correct: 'confirm' is an explicit re-call, not a human dialog.
    # A SetParam-only (param-edit) plan applies live; a structural plan (or plan/locked mode) asks first.
    from agent import permissions as _perm
    from agent.ops import AddFeature as _AF3
    from agent.ops import Plan as _Plan3
    from agent.ops import SetParam as _SP3
    _param_plan = _Plan3((_SP3("length", 80, 120),))
    _struct_plan = _Plan3((_AF3("clearance_hole", ("M8", (0, 0))),))
    _auto = {"mode": "auto", "param_edit": "auto", "structural": "confirm", "export": "confirm"}
    check("A3: permission policy classifies + gates by op class and mode",
          _perm.classify(_param_plan) == "param_edit" and _perm.classify(_struct_plan) == "structural"
          and _perm.decide("build", _param_plan, False, pol=_auto)[0] == "allow"
          and _perm.decide("build", _struct_plan, False, pol=_auto)[0] == "needs_confirmation"
          and _perm.decide("build", _struct_plan, True, pol=_auto)[0] == "allow"
          and _perm.decide("export", None, False, pol=_auto)[0] == "needs_confirmation"
          and _perm.decide("build", _param_plan, False, pol={**_auto, "mode": "plan"})[0] == "needs_confirmation"
          and _perm.decide("build", _param_plan, False, pol={**_auto, "mode": "locked"})[0] == "denied",
          "auto/plan/locked · param/structural/export")

    # Geometry spine — the S2 gate. Runs only when the OCCT kernel is installed; without
    # cadquery the pure-Python spine above is the gate (so CI stays green before the kernel lands).
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("  [skip] geometry gate — cadquery not installed (pure-Python spine is the gate)")
    else:
        from eval import harness, reference
        from eval.briefs import BRIEFS
        from geometry import GeometryService
        from toolkit.standards import bbox_gate

        g = GeometryService()
        bracket = reference.build(next(x for x in BRIEFS if x["id"] == "bracket"))
        length, width, height = g.bbox(bracket.geometry)
        tol = bbox_gate()
        check("bracket bbox 80×40×6 within gate",
              abs(length - 80) <= tol and abs(width - 40) <= tol and abs(height - 6) <= tol,
              f"got {length:.4f}×{width:.4f}×{height:.4f}")
        check("bracket has two holes", g.cylindrical_face_count(bracket.geometry) == 2)
        check("bracket solid is valid", g.is_valid(bracket.geometry))
        rate, _ = harness.run(reference.build)
        check("eval pass-rate harness reports 100% on the oracle", rate == 1.0, f"got {rate:.2f}")

        # R3 — deterministic params→geometry evaluator parity (DAG-EVAL). For every graph-expressible
        # frozen brief, the NO-LLM evaluator (replaying the recorded FeatureGraph onto GeometryService)
        # must match the closure oracle on bbox / cylindrical-face count / validity within the gate.
        from geometry.evaluator import evaluate, is_graph_expressible
        from toolkit.elements import recording
        _expr, _skipped = [], []
        for _brief in BRIEFS:
            with recording() as _gr:
                _oracle = reference.build(_brief)   # ops recorded as a side-effect of the oracle build
            if not is_graph_expressible(_gr):
                _skipped.append(_brief["id"])
                continue
            _ev = evaluate(_gr)
            _ob, _eb = g.bbox(_oracle.geometry), g.bbox(_ev)
            _ok = (all(abs(a - b) <= tol for a, b in zip(_ob, _eb))
                   and g.cylindrical_face_count(_ev) == g.cylindrical_face_count(_oracle.geometry)
                   and g.is_valid(_ev))
            _expr.append(_brief["id"])
            check(f"evaluator parity · {_brief['id']}", _ok,
                  f"oracle {tuple(round(x, 3) for x in _ob)} vs eval {tuple(round(x, 3) for x in _eb)}")
        check("evaluator: ≥6 briefs graph-expressible", len(_expr) >= 6, f"expressible={_expr}")
        print(f"  [info] evaluator parity: {len(_expr)} graph-expressible {_expr} · "
              f"{len(_skipped)} fall back to text-substitution {_skipped}")

        # R4 — content-hash cache + incremental set_param (tree-reduction). Editing one param rebuilds
        # EXACTLY the dirty descendant set; clean subtrees (an assembly's untouched base) come from cache.
        from geometry.evaluator import Evaluator, descendants
        from toolkit import assembly as _assembly, stack as _stack
        with recording() as _rbg:                              # bracket: length cascades to both holes
            _rb = box("_r4_bracket", 80, 40, 6)
            _clearance_hole(_rb, "M8", (-25, 0))
            _clearance_hole(_rb, "M8", (25, 0))
        _ebr = Evaluator(_rbg)
        _, _warm = _ebr.build()                                # warm the cache — first build is full
        _h, _rebuilt = _ebr.set_param("box#1", "length", 100)
        _dirty = descendants(_rbg, "box#1")
        check("R4 bracket: length edit rebuilds box + both holes only (== dirty set)",
              _warm == {"box#1", "hole#1", "hole#2"} and _rebuilt == _dirty == {"box#1", "hole#1", "hole#2"}
              and abs(g.bbox(_h)[0] - 100) <= tol,
              f"warm={sorted(_warm)} rebuilt={sorted(_rebuilt)} dirty={sorted(_dirty)}")
        with recording() as _rag:                              # assembly: resize the top plate
            _abase = box("base", 60, 60, 10)
            _atop = box("top", 40, 40, 10)
            _stack(_abase, _atop)
            _assembly("stacked", _abase, _atop)
        _eas = Evaluator(_rag)
        _eas.build()
        _h2, _rebuilt2 = _eas.set_param("box#2", "height", 20)
        _dirty2 = descendants(_rag, "box#2")
        check("R4 assembly: top resize rebuilds top+stack+compound, NOT base (== dirty set)",
              _rebuilt2 == _dirty2 == {"box#2", "stack#1", "assembly#1"} and "box#1" not in _rebuilt2,
              f"rebuilt={sorted(_rebuilt2)} dirty={sorted(_dirty2)}")
        _, _noop = _eas.set_param("box#1", "length", 60)       # set to current value → cache hit, no rebuild
        check("R4 unchanged param rebuilds nothing (content-key stable)", _noop == set(),
              f"rebuilt={sorted(_noop)}")

        import tempfile
        from backends import step as step_backend
        with tempfile.TemporaryDirectory() as td:
            sp = step_backend.compile(bracket, td)
            rl, rw, rh = step_backend.reimport_bbox(sp)
            check("STEP round-trips through OCCT (FreeCAD-openable)",
                  sp.exists() and sp.stat().st_size > 0
                  and abs(rl - 80) <= tol and abs(rw - 40) <= tol and abs(rh - 6) <= tol,
                  f"reimport bbox {rl:.3f}×{rw:.3f}×{rh:.3f}")

        # A7 — STL backend + printability critic. STL emits a valid mesh (registered per [H4]);
        # printability is N/A off, gates a print job on min-wall/envelope, and ADVISES on overhang —
        # verified fabricability for 3D printing (the print3d self-serve wedge).
        from agent.loop import Brief as _Brief
        from backends import by_name as _by_name, stl as _stl_backend
        from critic import panel as _pnl
        from toolkit import assembly as _asm, box as _bx, panel as _pnlpanel, place as _place
        with tempfile.TemporaryDirectory() as td:
            # a FRESH part — STL tessellation adds a triangulation that perturbs a shape's cached bbox,
            # so never tessellate the shared `bracket` the exact-dim checks below reuse.
            _stlp = _stl_backend.compile(_bx("a7stl", 30, 20, 8), td)
            check("STL backend emits a valid non-empty mesh (registered per [H4])",
                  _stlp.exists() and _stlp.stat().st_size > 100 and _by_name("stl") is not None)
        check("printability critic registered in the panel (no loop change)",
              any(getattr(c, "name", "") == "printability" for c in _pnl.critics()))
        check("printability is N/A when no print process is declared (inert for non-print parts)",
              any(c.check == "printability" and c.status.value == "n/a"
                  for c in _pnl.evaluate(_bx("pk", 60, 40, 20), _Brief(prompt="a bracket")).checks))
        _thin_c = _pnl.evaluate(_bx("thin", 40, 40, 0.5), _Brief(prompt="printed", process="fdm"))
        check("printability FAILS a thin-wall FDM part on print_min_wall (gates export)",
              not _thin_c.passed and any(c.check == "print_min_wall" and c.status.value == "fail"
                                         for c in _thin_c.checks))
        check("printability FAILS an oversize FDM part on the build envelope",
              any(c.check == "envelope" and c.status.value == "fail" for c in
                  _pnl.evaluate(_pnlpanel("big", 3000, 2000, 200), _Brief(prompt="p", process="fdm")).checks))
        _cap = _bx("cap", 60, 60, 10)
        _place(_cap, (0, 0, 40))
        _cant_c = _pnl.evaluate(_asm("T", _bx("post", 20, 20, 40), _cap), _Brief(prompt="p", process="fdm"))
        check("printability overhang is ADVISORY — flags support, does NOT block export",
              _cant_c.passed and any(c.check == "overhang" and "support" in c.message
                                     for c in _cant_c.checks))

        from backends import drawing as drawing_backend
        with tempfile.TemporaryDirectory() as td:
            dp = drawing_backend.compile(bracket, td)
            txt = dp.read_text()
            check("drawing exports a dimensioned HLR SVG",
                  dp.suffix == ".svg" and "<svg" in txt and "length = 80" in txt,
                  f"{dp.name}, {len(txt)} bytes")

        try:
            import ezdxf  # noqa: F401
            from backends import shopdrawing as shop_backend
            with tempfile.TemporaryDirectory() as td:
                dxf = shop_backend.compile(bracket, td)
                doc = ezdxf.readfile(str(dxf))
                msp = doc.modelspace()
                layers = {e.dxf.layer for e in msp}
                dimlfac = doc.dimstyles.get("LUDWIG").dxf.dimlfac
                true_vals = {round(d.get_measurement() * dimlfac) for d in msp.query("DIMENSION")}
                circles = len(msp.query("CIRCLE"))
                check("shop drawing: conventioned multi-view DXF, dims read true mm",
                      dxf.suffix == ".dxf"
                      and {"VISIBLE", "HIDDEN", "CENTRE", "DIMENSION"} <= layers
                      and circles == 2                       # two holes drawn as circles in the plan
                      and {80, 40, 6} <= true_vals,          # overall L/W/H recovered exactly through DIMLFAC
                      f"layers={sorted(layers)} circles={circles} dims={sorted(true_vals)}")
        except ImportError:
            print("  [skip] shop-drawing check — ezdxf not installed")

        # R19 — Stair: a saw-tooth flight extruded as ONE prism (no booleans). bbox = run × width × ftf.
        from toolkit import stair as _stair
        _st = _stair("selftest_stair", rise=170, going=280, width=1000, riser_count=17)
        _sl, _sw, _sh = g.bbox(_st.geometry)
        check("stair bbox = run×width×floor-to-floor within gate",
              abs(_sl - 17 * 280) <= tol and abs(_sw - 1000) <= tol and abs(_sh - 17 * 170) <= tol,
              f"got {_sl:.1f}×{_sw:.1f}×{_sh:.1f} (want {17*280}×1000×{17*170})")
        check("stair is a valid solid with no cylindrical faces",
              g.is_valid(_st.geometry) and g.cylindrical_face_count(_st.geometry) == 0,
              f"valid={g.is_valid(_st.geometry)} cyl={g.cylindrical_face_count(_st.geometry)}")

        # R20 — AD-K compliance critic (the verified-fabricability moat). A compliant general-access
        # stair passes the panel; an over-pitch one fails it — deterministically, no loop change. And
        # the new critic is NA for non-stairs, so pre-existing critiques are unaffected.
        from agent.loop import Brief
        from critic import panel as _panel
        _ok_stair = _stair("ok_stair", rise=170, going=280, width=1000, riser_count=17)   # general-compliant
        _bad_stair = _stair("bad_stair", rise=240, going=180, width=1000, riser_count=12)  # over-pitch / over-rise
        _general = Brief(prompt="general access stair", use_class="general")
        _ok_crit = _panel.evaluate(_ok_stair, _general)
        check("compliant stair passes the panel (AD-K general)", _ok_crit.passed,
              f"failures={[c.check for c in _ok_crit.failures]}")
        _bad_crit = _panel.evaluate(_bad_stair, _general)
        check("over-pitch stair FAILS the compliance critic",
              not _bad_crit.passed and any(c.check in ("pitch", "rise") and c.status.value == "fail"
                                           for c in _bad_crit.checks),
              f"failures={[c.check for c in _bad_crit.failures]}")
        _br_crit = _panel.evaluate(bracket, Brief(prompt="a bracket"))
        check("compliance is NA for non-stairs (bracket panel unaffected)",
              _br_crit.passed and any(c.check == "stair_compliance" and c.status.value == "n/a"
                                      for c in _br_crit.checks))

        # Dimensional fallback: with NO brief-declared dims (a gallery seed / adopt / bare compile), the
        # critic self-verifies the element's registered EXTENT dims against the measured solid — real
        # coverage instead of a vacuous n/a (so the demo's headline check actually runs). The bracket has
        # no declared dims here, yet dimensional must produce PASS extent checks, not a single n/a.
        _dim = [c for c in _br_crit.checks if c.check.startswith("dim")]
        check("dimensional self-verifies registered extents when no dims declared",
              {c.check for c in _dim} == {"dim:length", "dim:width", "dim:height"}
              and all(c.status.value == "pass" for c in _dim),
              f"got {[(c.check, c.status.value) for c in _dim]}")

        # A cylinder's diameter and a panel's thickness are verified against the MEASURED solid, not just
        # their registered value — so the check is real, not vacuous. flange ⌀100 self-verifies to PASS;
        # a DECLARED ⌀90 on the same ⌀100 solid must FAIL (measured 100 ≠ declared 90).
        from toolkit import cylinder as _cyl
        _fl = _cyl("fl", 100, 12)
        _fl_ok = _panel.evaluate(_fl, Brief(prompt="flange")).checks
        _fld = next((c for c in _fl_ok if c.check == "dim:diameter"), None)
        check("cylinder diameter self-verifies against the measured solid",
              _fld is not None and _fld.status.value == "pass")
        _fl_bad = _panel.evaluate(_fl, Brief(prompt="", named_dims={"diameter": 90.0}))
        check("a declared diameter that mismatches the solid FAILS (non-vacuous)",
              any(c.check == "dim:diameter" and c.status.value == "fail" for c in _fl_bad.checks))

        # R22 — Wall + Opening: a generic rect boolean cuts a door/window void; the wall stays a valid
        # solid with less material, and the Opening is hosted via a 'hosts' relation.
        from toolkit import opening as _opening, wall as _wall
        _w = _wall("selftest_wall", 3000, 2400, 200)
        _vol_solid = g.volume(_w.geometry)
        _op = _opening(_w, 900, 2100, (0, 0))     # a door-sized void through the centre
        check("wall + opening: void reduces volume, wall stays valid",
              g.is_valid(_w.geometry) and g.volume(_w.geometry) < _vol_solid - 1.0,
              f"vol {g.volume(_w.geometry):.0f} < {_vol_solid:.0f}")
        check("opening is type 'Opening' hosted by the wall",
              _op.type == "Opening"
              and any(r.kind == "hosts" and r.target_id == _op.id for r in _w.relations))

        # R28 — sketch→extrude: an L-section compiles from a FULLY-CONSTRAINED sketch to an exact solid.
        from backends import step as _step_b
        _lp = reference.build(next(x for x in BRIEFS if x["id"] == "l_profile"))
        _ll, _lw, _lh = g.bbox(_lp.geometry)
        check("L-profile bbox 80×60×100 from a constrained sketch",
              abs(_ll - 80) <= tol and abs(_lw - 60) <= tol and abs(_lh - 100) <= tol,
              f"got {_ll:.1f}×{_lw:.1f}×{_lh:.1f}")
        check("L-profile section area ≈ 1300 mm² (t·(Lx+Ly−t)) and solid valid",
              g.is_valid(_lp.geometry) and abs(g.volume(_lp.geometry) / 100.0 - 1300) <= 1.0,
              f"section {g.volume(_lp.geometry) / 100.0:.1f}")
        with tempfile.TemporaryDirectory() as _td:
            _lsp = _step_b.compile(_lp, _td)
            _rl, _rw, _rh = _step_b.reimport_bbox(_lsp)
            check("L-profile STEP round-trips through OCCT",
                  abs(_rl - 80) <= tol and abs(_rw - 60) <= tol and abs(_rh - 100) <= tol,
                  f"reimport {_rl:.1f}×{_rw:.1f}×{_rh:.1f}")

        # Mass + material cost from the EXACT (holes-subtracted) solid volume × standards density/price —
        # the "what will this weigh and cost to make" a fabricator/buyer asks. Only when the type maps to
        # a material (a solid primitive like the stair stays out — its simplified geometry would mislead).
        from webapp.service import _mass_estimate as _mest
        _be = _mest(bracket, g)
        check("estimate: bracket mass from exact B-rep volume × steel density + a material cost",
              _be is not None and abs(_be["mass_kg"] - 0.145) < 0.01 and _be["material"] == "Steel"
              and _be["grade"] == "S355" and _be.get("cost") is not None,
              f"{_be.get('mass_kg')} kg · {_be.get('cost')} {_be.get('currency')}")

        # cylinder primitive — the round part class (flanges/shafts/washers), a robust OCCT primitive.
        from agent.loop import execute as _ex2
        from webapp import gallery as _gal2
        _fl, _ = _ex2(_gal2.program_for("flange"))
        _flbb = g.bbox(_fl.geometry)
        check("cylinder: flange ⌀100×12 builds with 6 cylindrical faces (rim + bore + 4 bolts), valid",
              abs(_flbb[0] - 100) <= tol and abs(_flbb[2] - 12) <= tol and g.is_valid(_fl.geometry)
              and g.cylindrical_face_count(_fl.geometry) == 6,
              f"bbox {tuple(round(v, 1) for v in _flbb)} · {g.cylindrical_face_count(_fl.geometry)} cyl faces")

        # machining features (fillet / chamfer / slot / counterbore) — element-API ops the live eval's
        # feature briefs demand. Each builds a valid solid; a featured part drops to the substitution
        # preview (an edge op isn't in the evaluator) — verified graph-cleared, so no wrong fast-path.
        from toolkit import box as _bx
        from toolkit import chamfer as _ch
        from toolkit import counterbore as _cb
        from toolkit import fillet as _fi
        from toolkit import hole as _ho
        from toolkit import slot as _sl
        _fb = _fi(_bx("fb", 80, 40, 6), 5)
        _cs = _ch(_ho(_bx("cs", 30, 30, 12), 10.0, (0, 0)), 2, selector="bore")
        _sp = _sl(_bx("sp", 120, 60, 10), 10, 40)
        _cp = _cb(_cb(_bx("cp", 80, 50, 10), 6.6, 11, 5, (-20, 0)), 6.6, 11, 5, (20, 0))
        check("features: fillet/chamfer/slot/counterbore each build a valid solid + clear the fast-path graph",
              all(g.is_valid(e.geometry) for e in (_fb, _cs, _sp, _cp)) and _fb.graph is None
              and g.volume(_sp.geometry) < 120 * 60 * 10 and g.cylindrical_face_count(_cp.geometry) == 4,
              f"cbore cyl faces {g.cylindrical_face_count(_cp.geometry)}")

        # R29 — section op + void-aware cut profile. A YZ cut keeps half the bracket (40×40×6) with one
        # outer loop (240 mm²). A horizontal (z) cut shows the plate plan with the two holes as INNER
        # loops — the void-aware case. (A through-hole splits the section rather than nesting; the
        # honest void-aware profile is the cut across the holes' axis — see docs/FINDINGS.md.)
        _yz = g.section(bracket.geometry, axis="x", offset=0.0, keep="+")
        _ybb = g.bbox(_yz)
        _yp = g.section_profile(bracket.geometry, axis="x", offset=0.0)
        check("section: YZ cut keeps 40×40×6 with one outer loop ≈240 mm²",
              abs(_ybb[0] - 40) <= tol and abs(_ybb[1] - 40) <= tol and abs(_ybb[2] - 6) <= tol
              and len(_yp["outer"]) == 1 and abs(g.loop_area(_yp["outer"][0]) - 240) <= 1.0,
              f"bbox {tuple(round(v, 1) for v in _ybb)} outer {[round(g.loop_area(l), 1) for l in _yp['outer']]}")
        _zp = g.section_profile(bracket.geometry, axis="z", offset=0.0)
        check("section: horizontal cut = plate outline (≈3200 mm²) + two hole inner loops",
              len(_zp["outer"]) == 1 and abs(g.loop_area(_zp["outer"][0]) - 3200) <= 1.0
              and len(_zp["inners"]) == 2,
              f"outer {[round(g.loop_area(l), 1) for l in _zp['outer']]} inners {len(_zp['inners'])}")

        # R30 — section DRAWING backend: a poché-hatched, dimensioned cut sheet (the moat's 2nd sheet).
        # The default centroidal-longitudinal plane cuts the bracket through its thickness (XY plane),
        # so the poché is the 80×40 plate with the two M8 holes punched as white voids (island hatch).
        import ezdxf as _ezdxf
        from backends import by_name as _by_name
        _secb = _by_name("section")
        check("section backend registered (added by import, no loop change)", _secb is not None)
        with tempfile.TemporaryDirectory() as _td:
            _sp = _secb.compile(bracket, _td)
            _doc = _ezdxf.readfile(str(_sp))
            _msp = _doc.modelspace()
            _hatch = [e for e in _msp if e.dxftype() == "HATCH"]
            _lyr = {ly.dxf.name for ly in _doc.layers}
            _dims = [e for e in _msp if e.dxftype() == "DIMENSION"]
            _cut = [e for e in _msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "CUT"]
            check("section DXF: ≥1 poché HATCH, CUT+POCHE layers, cut boundary + 2 hole voids",
                  _sp.name == "bracket_section.dxf" and len(_hatch) >= 1
                  and {"CUT", "POCHE"} <= _lyr and len(_cut) == 3,
                  f"{len(_hatch)} hatch · layers {sorted(_lyr & {'CUT', 'POCHE', 'BEYOND'})} · {len(_cut)} cut loops")
            check("section carries true-mm dimensions (DIMLFAC), preview PNG emitted",
                  len(_dims) >= 2 and _sp.with_suffix(".png").exists(),
                  f"{len(_dims)} dims")

        # R33 — a live, re-promptable cut plane. ONE plane resolver: a DECLARED section (toolkit.section)
        # is honoured identically by the R30 drawing backend and the live mesh cut. The token-free webapp
        # payload returns a non-empty section mesh for the bracket — no LLM, no backends in the hot path.
        from agent.loop import execute as _exec
        from backends.section import _section_spec as _spec
        from webapp import gallery as _gal
        from webapp.service import section_to_result as _sec_res
        _decl_el, _ = _exec('element = box("b", 80, 40, 6)\nsection(element, axis="y", offset=15)\n')
        check("R33: a declared section plane is honoured exactly by the backend resolver (y @ 15)",
              _spec(_decl_el) == ("y", 15.0), f"{_spec(_decl_el)}")
        _live = _sec_res(_gal.program_for("bracket"))
        check("R33: token-free live cut returns a non-empty section mesh for the bracket",
              bool(_live.get("ok")) and len(_live["mesh"]["indices"]) >= 3 and _live["axis"] in ("x", "y", "z"),
              f"{_live.get('axis')} @ {_live.get('offset')} · "
              f"{len(_live['mesh']['indices']) // 3 if _live.get('mesh') else 0} tris")

        # R31 — section/plan as a derived SKETCH view. A sketch-extruded solid sections ⟂ its EXTRUDE
        # axis by default, recovering the authored 2D profile: the L-profile cut at mid-height is the
        # true L (6 corners, ≈1300 mm²) — not a rectangle through the wrong axis — poché'd into the DXF.
        _lax, _loff = _spec(_lp)
        _lprof = g.section_profile(_lp.geometry, axis=_lax, offset=_loff)["outer"]
        check("R31: L-profile sections ⟂ its extrude axis, recovering the authored L (6 pts · ≈1300 mm²)",
              _lax == "z" and len(_lprof) == 1 and 5 <= len(_lprof[0]) <= 7
              and abs(g.loop_area(_lprof[0]) - 1300) <= 5.0,
              f"{_lax}@{_loff:g} · {len(_lprof[0]) if _lprof else 0} pts · "
              f"{g.loop_area(_lprof[0]) if _lprof else 0:.0f} mm²")
        with tempfile.TemporaryDirectory() as _td:
            _lps = _secb.compile(_lp, _td)
            _lmsp = _ezdxf.readfile(str(_lps)).modelspace()
            _lcut = [e for e in _lmsp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "CUT"]
            _lh = [e for e in _lmsp if e.dxftype() == "HATCH"]
            check("R31: the L section is drawn into the DXF (poché + L-shaped cut boundary)",
                  len(_lcut) == 1 and 5 <= len(list(_lcut[0].get_points())) <= 8 and len(_lh) >= 1,
                  f"{len(_lcut)} cut loop(s) · {len(list(_lcut[0].get_points())) if _lcut else 0} pts · {len(_lh)} hatch")

        # R34 — live sketch edit. Dragging a sketch DISTANCE dim re-solves + re-extrudes in-process
        # (no files, no LLM) and returns the new solid mesh AND the solved 2D profile (the derived
        # section) — 3D extrude and 2D sketch move in lockstep. The commit is token-free too (1-literal diff).
        from webapp.service import edit_to_result as _edit_res
        from webapp.service import preview_edit as _prev
        _lp_prog = _gal.program_for("l_profile")
        _pv = _prev(_lp_prog, "d_L0", 80, 120)
        check("R34: a sketch-dim drag re-solves live — 3D mesh + 2D profile, token-free",
              bool(_pv.get("ok")) and _pv.get("engine") == "sketch-resolve"
              and _pv["bbox"]["length"] == 120 and len(_pv["mesh"]["indices"]) >= 3
              and _pv.get("sketch2d") and len(_pv["sketch2d"]) == 6,
              f"len {_pv.get('bbox', {}).get('length')} · sketch2d "
              f"{len(_pv['sketch2d']) if _pv.get('sketch2d') else 0} pts · {_pv.get('engine')}")
        with tempfile.TemporaryDirectory() as _td:
            _cm = _edit_res(_lp_prog, "make the leg 120 mm",
                            param={"name": "d_L0", "old": 80, "new": 120}, out=_td, allow_llm=False)
        check("R34: the sketch-dim commit is a token-free minimal diff (no LLM, demo-safe)",
              _cm.get("fast") is True and _cm.get("diff", {}).get("added") == 1 and "fatal" not in _cm,
              f"fast={_cm.get('fast')} · +{_cm.get('diff', {}).get('added')} line · id {_cm.get('id')}")

        # R15 — Op-API build path: render a reviewed Plan → execute → verify → assemble (fab gate intact).
        # A 3-op bracket plan built onto an empty program produces the verified solid + STEP/IFC; a +3-line
        # diff; and the fab gate withholds STEP if the critic doesn't all-pass. No LLM, no exec of model code.
        from pathlib import Path as _Path

        from agent.ops import AddElement as _AE
        from agent.ops import AddFeature as _AF
        from agent.ops import Plan as _Plan
        from agent.ops import SetParam as _SP
        from webapp.service import build_to_result as _build
        _bracket_plan = _Plan((_AE("box", "bracket", (80, 40, 6)),
                               _AF("clearance_hole", ("M8", (-25, 0))),
                               _AF("clearance_hole", ("M8", (25, 0)))))
        with tempfile.TemporaryDirectory() as _td:
            _br = _build("", _bracket_plan, out=_td)
            check("R15: a reviewed 3-op plan builds a verified solid with STEP+IFC (+3-line diff)",
                  _br.get("passed") is True and _br.get("diff", {}).get("added") == 3
                  and "step" in _br["artifacts"] and "ifc" in _br["artifacts"]
                  and (_Path(_td) / _br["artifacts"]["step"]).exists(),
                  f"passed={_br.get('passed')} +{_br.get('diff', {}).get('added')} artifacts={sorted(k for k in _br['artifacts'] if k in ('step', 'ifc', 'dxf'))}")
            # a SetParam build edits an existing program + hands back an invertible plan (undo)
            _edit = _build(_br["program"], _Plan((_SP("length", 80, 120),)), out=_td)
            check("R15: a SetParam build edits the solid and returns an invertible plan (undo)",
                  _edit.get("passed") is True and _edit["bbox"]["length"] == 120
                  and _edit["inverse"] and _edit["inverse"][0]["new"] == 80,
                  f"len={_edit.get('bbox', {}).get('length')} inverse={_edit.get('inverse')}")
            # R16 (kernel half): a PARSED JSON plan builds a verified solid — parse → render → execute → verify
            _pb = _build("", _parse(_json_plan), out=_td)
            check("R16: a parsed JSON plan builds a verified solid (parse → build → verify)",
                  _pb.get("passed") is True and "step" in _pb["artifacts"], f"passed={_pb.get('passed')}")
            # R18: /api/build's service path — build a client-reviewed plan from raw JSON ops, token-free
            from webapp.service import build_from_ops as _bfo
            _wb = _bfo("", _json_plan, out=_td, confirm=True)   # a reviewed structural build (A3 gate)
            check("R18: build_from_ops builds a verified solid from client JSON ops (token-free)",
                  _wb.get("passed") is True and _wb.get("diff", {}).get("added") == 3
                  and "step" in _wb["artifacts"], f"passed={_wb.get('passed')}")
            # A1 — a REAL built payload carries the contract version (the _versioned decorator, end to end)
            check("A1: a real result payload carries schema_version",
                  _wb.get("schema_version") == _svc.SCHEMA_VERSION, f"got {_wb.get('schema_version')!r}")

        # R13 — hole-position edit: move a hole deterministically (substitute its literal + re-bore),
        # gated by a cylindrical-centre re-measure — token-free, the plan-drag analogue of face-drag.
        from webapp.service import hole_move_to_result as _hmr
        from webapp.service import preview_hole_move as _phm
        _hp = _phm(_gal.program_for("bracket"), (-25, 0), (-30, 8))
        check("R13: a hole move re-bores live and confirms the new centre (token-free)",
              bool(_hp.get("ok")) and _hp.get("engine") == "hole-move" and len(_hp["mesh"]["indices"]) >= 3
              and any(abs(h["at"][0] + 30) < 0.5 and abs(h["at"][1] - 8) < 0.5 for h in _hp.get("holes", [])),
              f"holes {[h['at'] for h in _hp.get('holes', [])]}")
        with tempfile.TemporaryDirectory() as _td:
            _hc = _hmr(_gal.program_for("bracket"), (-25, 0), (-30, 8), out=_td)
        check("R13: the hole-move commit is a +1/−1 diff; a hole dragged off the part is refused",
              _hc.get("fast") is True and _hc.get("diff", {}).get("added") == 1
              and _phm(_gal.program_for("bracket"), (-25, 0), (-500, 0)).get("ok") is False,
              f"fast={_hc.get('fast')} · off-part refused")

        try:
            import ifcopenshell  # noqa: F401
            from backends import ifc as ifc_backend
            with tempfile.TemporaryDirectory() as td:
                ip = ifc_backend.compile(bracket, td)
                summary = ifc_backend.reimport_summary(ip)
                check("IFC exports + round-trips (IfcOpenShell)",
                      ip.exists() and summary["schema"] == "IFC4"
                      and summary["element_classes"] == ["IfcBuildingElementProxy"],
                      str(summary))
        except ImportError:
            print("  [skip] IFC check — ifcopenshell not installed")

    # M1 (v2 harness) — ludwig.toml config resolver + telemetry RunStore. Pure stdlib (no kernel,
    # no third-party dep), so these run on bare Python. The config_hash pins a run's settings (WS7);
    # the RunStore is the trajectory-dataset plumbing WS7 builds on.
    from agent import config as _cfg
    _c0 = _cfg.HarnessConfig()
    check("M1 config: defaults resolve (d=3 b=3 veri=0.5, max_calls=60)",
          _c0.search.depth == 3 and _c0.search.branch == 3 and _c0.search.veri_ratio == 0.5
          and _c0.budget.max_calls == 60 and _c0.telemetry.runs_dir == "runs")
    _c1 = _cfg.load_config(overrides={"search.depth": "5", "budget.max_calls": "30",
                                      "telemetry.enabled": "false"})
    check("M1 config: CLI overrides coerce by field type (int/bool)",
          _c1.search.depth == 5 and _c1.budget.max_calls == 30 and _c1.telemetry.enabled is False)
    check("M1 config: config_hash is stable, and moves when a value changes",
          _cfg.HarnessConfig().config_hash() == _cfg.HarnessConfig().config_hash()
          and _c0.config_hash() != _c1.config_hash())
    try:                                    # unknown override key → KeyError (not ValueError)
        _cfg.load_config(overrides={"search.bogus": 1})
        _bad_key_rejected = False
    except KeyError:
        _bad_key_rejected = True
    check("M1 config: out-of-range value (ValueError) + unknown key (KeyError) are both rejected",
          _raises(lambda: _cfg.load_config(overrides={"search.veri_ratio": "2.0"})) and _bad_key_rejected)
    import tempfile as _tempfile   # local: the kernel-gated block's import may not have run on bare Python
    from telemetry.store import RunStore as _RunStore
    with _tempfile.TemporaryDirectory() as _rd:
        _rs = _RunStore("selftest_run", runs_dir=_rd)
        _rs.write_manifest({"config_hash": _c0.config_hash(), "seed": 0})
        _rs.extend_events([{"type": "brief", "text": "bracket"}, {"type": "selection", "kept": "b1"}])
        _sha_a = _rs.put_media(b"fake-render-bytes", ext="png")
        _sha_b = _rs.put_media(b"fake-render-bytes", ext="png")   # identical → content-addressed dedup
        check("M1 telemetry: RunStore round-trips manifest + trajectory + content-addressed media",
              _rs.read_manifest()["run_id"] == "selftest_run"
              and [e["type"] for e in _rs.read_events()] == ["brief", "selection"]
              and _sha_a == _sha_b and _rs.media_path(_sha_a).exists())

    # WS2 (v2 harness) — deliberative branch-and-prune. The scheduler math is pure; the driver is
    # exercised token-free with a scripted mock (real model/kernel primitives are injected in the loop).
    # A "program" is p:<quality>, lower better, 0 passes; score mirrors _weighted_failures.
    from agent import search as _search
    check("WS2 search: plan_levels is the d×b ideal unbudgeted, and splits by veri_ratio under a ceiling",
          _search.plan_levels(3, 3, 0.5) == [3, 3, 3]
          and sum(_search.plan_levels(3, 3, 0.5, max_calls=5)) <= 5
          and _search.plan_levels(4, 4, 0.25, 10)[0] > _search.plan_levels(4, 4, 0.75, 10)[0])
    _sit = iter([5, 4, 3, 2, 6, 1, 0, 9, 4])   # level0 best 3 → 1 → 0 (converges at level 2)

    class _SelftestCrit:
        def __init__(self, q):
            self.quality = q
            self.passed = (q == 0)
            self.failures = []

    _sr = _search.search(
        None, depth=3, branch=3, keep_k=1, veri_ratio=0.5,
        propose=lambda b: f"p:{next(_sit)}", refine=lambda parent, b: f"p:{next(_sit)}",
        execute=lambda p: ((None, "err") if int(p.split(":")[1]) < 0 else (int(p.split(":")[1]), None)),
        verify=lambda ir, b: _SelftestCrit(ir),
        score=lambda c: (1, 0) if c is None else (0, c.quality))
    check("WS2 search: branch-and-prune refines to the passing branch (converged, 9 calls)",
          _sr.passed and _sr.reason == "converged" and _sr.calls_used == 9 and _sr.best.program == "p:0")

    ok = all(passed for _, passed, _ in checks)
    for label, passed, detail in checks:
        mark = "ok  " if passed else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail and not passed else ""))
    print(("PASS" if ok else "FAIL") + f" — {sum(p for _, p, _ in checks)}/{len(checks)} checks")
    return 0 if ok else 1


def _run_eval_mcp(briefs=None):
    """External-agent pass-rate (A4, the second tracked number): drive each frozen brief through the MCP
    `ludwig_compile` tool over ONE stdio session — Ludwig as someone else's tool — execute the returned
    program, and grade it with the SAME geometric gate as native. The gap to the native live rate is how
    much of Ludwig's reliability survives the harness boundary (§8).

    Robust to inference throttling (the A4 measurement artifact, FINDINGS 2026-07-04): the run *paces*
    itself between briefs and *retries throttle-shaped* failures (empty program / tool error / timeout —
    the CLI session limit, not Ludwig) with real backoff, so the number reflects codegen reliability,
    not the provider's rate window. A genuine geometry miss (built, off dims) is NOT retried — that is
    an honest first-pass fail, counted exactly as native `--live` counts it. Tunables:
      LUDWIG_EVAL_PACE_S    inter-brief pacing seconds        (default 6)
      LUDWIG_EVAL_RETRIES   throttle retries per brief        (default 3; backoff 20s→40s→80s)
    """
    import asyncio
    import json as _json
    import os as _os
    import sys as _sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from agent.loop import execute
    from eval import harness
    from eval.briefs import BRIEFS
    from geometry.service import GeometryService
    from toolkit.standards import bbox_gate

    briefs = briefs if briefs is not None else BRIEFS
    geom, tol = GeometryService(), bbox_gate()
    pace_s = float(_os.environ.get("LUDWIG_EVAL_PACE_S", "6"))
    retries = int(_os.environ.get("LUDWIG_EVAL_RETRIES", "3"))

    async def _attempt(s, b):
        """One compile→execute→grade pass. Returns (ok, reason, throttled)."""
        try:
            res = await asyncio.wait_for(s.call_tool("ludwig_compile", {"brief": b["prompt"]}), 420)
            d = res.structuredContent or _json.loads(res.content[0].text)
            prog = d.get("program") or ""
            if not prog:                       # codegen produced nothing — throttle-shaped, retry it
                return False, "no-program (codegen empty — inference rate/session limit?)", True
            el, err = execute(prog)
            if el is None:                     # a program that won't build is a REAL codegen miss, not throttle
                return False, f"build-error: {err}", False
            if not harness.geometric_pass(el, b, geom, tol):
                return False, "geom-miss (built, but off the declared dims/holes)", False
            return True, "", False
        except Exception as e:                 # tool error / timeout = harness/inference artifact, retry it
            return False, f"tool-error: {type(e).__name__}: {e}", True

    async def _drive():
        params = StdioServerParameters(command=_sys.executable, args=["cli.py", "mcp"], cwd=".")
        out, retried = [], 0
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await asyncio.wait_for(s.initialize(), 30)
                for i, b in enumerate(briefs):
                    ok = reason = None
                    for attempt in range(retries + 1):
                        ok, reason, throttled = await _attempt(s, b)
                        if ok or not throttled:
                            break              # success, or an HONEST geometry/build miss — do not burn retries
                        if attempt < retries:
                            retried += 1
                            backoff = 20 * (2 ** attempt)   # 20s, 40s, 80s — spans the rate window
                            print(f"  … {b['id']}: throttle-shaped fail (try {attempt + 1}/{retries + 1}), "
                                  f"backing off {backoff}s", flush=True)
                            await asyncio.sleep(backoff)
                    out.append((b["id"], ok, reason))
                    print(f"  [{'ok  ' if ok else 'FAIL'}] {b['id']}"
                          + (f" — {reason}" if not ok else ""), flush=True)
                    if pace_s and i < len(briefs) - 1:
                        await asyncio.sleep(pace_s)         # pace so we don't burst the limit in the first place
        return out, retried

    results, retried = asyncio.run(_drive())
    rate = sum(o for _, o, _ in results) / len(results) if results else 0.0
    if retried:
        print(f"  (recovered through {retried} throttle-retr{'y' if retried == 1 else 'ies'}; "
              "set LUDWIG_EVAL_PACE_S / LUDWIG_EVAL_RETRIES to tune)", flush=True)
    return rate, results


def mine_repairs(*, rounds: int = 2) -> int:
    """--mine-repairs (A5): run the full loop over the MINING pool (`eval/pool.py`, disjoint from the
    frozen set) and record every fail→pass repair into the corpus (`store/repairs.sqlite`). Costs live
    inference. This BUILDS the corpus; measuring its effect is `--eval --live --repair` with
    `LUDWIG_REPAIR_CORPUS=on` vs `off`. No frozen brief is ever mined (no train-on-test)."""
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("mining needs the OCCT kernel (`pip install cadquery`).")
        return 1
    from agent.loop import Brief, run
    from eval.pool import POOL
    from store import repairs

    conn = repairs.connect()
    before = conn.execute("SELECT COUNT(*) FROM repair").fetchone()[0]
    mined = 0
    for b in POOL:
        res = run(Brief.from_dict(b), rounds=rounds, mine=b["id"])   # mine=id → record fail→pass pairs
        status = "pass" if res.passed else "FAIL"
        print(f"  [{status}] {b['id']} · {res.rounds} repair round(s)")
    after = conn.execute("SELECT COUNT(*) FROM repair").fetchone()[0]
    mined = after - before
    print(f"mined {mined} new (failure→fix) pair(s) into {repairs.DEFAULT_PATH.name} "
          f"({after} total). Measure the effect: LUDWIG_REPAIR_CORPUS=on cli.py --eval --live --repair.")
    return 0


def run_eval(*, live: bool = False, repair: bool = False, via_mcp: bool = False) -> int:
    """First-pass geometric pass-rate over the frozen held-out brief set ([H6]).

    Default uses the deterministic reference oracle (no tokens). `--live` swaps in real LLM codegen;
    `--live --repair` measures the post-repair rate (the full loop + critic panel) — the number that
    reflects what the loop actually ships. `--mcp` drives the frozen briefs through the MCP server (the
    external-agent pass-rate, A4) — real inference, needs the MCP SDK.
    """
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("cadquery not installed — the eval harness needs the OCCT kernel "
              "(`pip install cadquery`). See BRIEF.md §4.")
        return 1
    if via_mcp:
        try:
            import mcp as _mcp_sdk  # noqa: F401
        except ImportError:
            print("the --mcp eval needs the MCP SDK (`pip install mcp`).")
            return 1
        rate, results = _run_eval_mcp()   # prints each brief live (paced + throttle-retried)
        passed = sum(o for _, o, _ in results)
        artifacts = sum(1 for _, o, r in results if not o and r.startswith(("tool-error", "no-program")))
        print(f"external-agent pass-rate (via MCP ludwig_compile): {rate * 100:.0f}%  ({passed}/{len(results)})")
        if artifacts:
            print(f"  caveat: {artifacts} fail(s) STILL throttle-shaped after retries (empty program / tool "
                  "error, not geometry) — raise LUDWIG_EVAL_RETRIES / LUDWIG_EVAL_PACE_S and re-run for the clean number.")
        return 0 if rate == 1.0 else 1
    from eval import harness
    if live:
        from eval import llm as builder_mod
        if repair:
            builder, label = builder_mod.build_repaired, "LIVE LLM codegen, post-repair"
        else:
            builder, label = builder_mod.build, "LIVE LLM codegen, first-pass"
    else:
        from eval import reference
        builder, label = reference.build, "reference oracle"

    rate, results = harness.run(builder)
    for bid, ok in results:
        print(f"  [{'ok  ' if ok else 'FAIL'}] {bid}")
    passed = sum(o for _, o in results)
    print(f"geometric pass-rate ({label}): {rate * 100:.0f}%  ({passed}/{len(results)})")
    return 0 if rate == 1.0 else 1


def compile_prompt(prompt: str, *, candidates: int = 1, rounds: int = 2,
                   search: bool = False, cfg=None) -> int:
    """The compile path: prompt → generated program → executed IR (BRIEF §5, S3 gate).

    With `search=True` the prompt is compiled through the WS2 deliberative branch-and-prune search
    (`agent.loop.run_search`) using the resolved `cfg` (an `agent.config.HarnessConfig`); otherwise the
    default linear loop (`candidates` proposals + `rounds` repair) runs, byte-unchanged.
    """
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("cadquery not installed — compiling needs the OCCT kernel (`pip install cadquery`).")
        return 1
    from agent.loop import Brief, run, run_search
    from geometry import GeometryService

    brief = Brief(prompt=prompt)
    if search:
        from agent.config import load_config
        cfg = cfg or load_config()
        print(f"› deliberative search: {prompt}\n  d={cfg.search.depth} b={cfg.search.branch} "
              f"keep_k={cfg.search.keep_k} veri_ratio={cfg.search.veri_ratio} "
              f"max_calls={cfg.budget.max_calls}\n")
        res = run_search(brief, cfg)
    else:
        print(f"› compiling: {prompt}\n")
        res = run(brief, candidates=candidates, rounds=rounds)
    print("--- program ---")
    print(res.program)
    print("\n--- result ---")
    if res.ir is None:
        print(f"FAILED to build an Element: {res.error}")
        return 1
    length, width, height = GeometryService().bbox(res.ir.geometry) if res.ir.geometry else (0.0, 0.0, 0.0)
    print(f"built {res.ir.id!r}: bbox {length:.3f}×{width:.3f}×{height:.3f} mm · "
          f"{len(res.ir.manifest)} named dims · {res.rounds} "
          f"{'model call(s)' if search else 'repair round(s)'}")
    for c in (res.critique.checks if res.critique else []):
        print(f"  [{c.status.value:4}] {c.check}" + (f" — {c.message}" if c.message else ""))

    # Persist the recipe (the source of truth) and, if the critic passed, compile through all backends.
    from pathlib import Path
    from backends import compile as compile_all
    out = Path("out")
    out.mkdir(exist_ok=True)
    recipe = out / f"{res.ir.id}.py"
    recipe.write_text(res.program + "\n")
    if res.passed:  # pre-export validation hook (BRIEF §5): no fabrication file leaves on a failing critic
        artifacts = compile_all(res.ir, out)
        parts = [f"wrote recipe {recipe}"]
        _LABELS = {"step": "STEP", "ifc": "IFC", "drawing": "SVG preview",
                   "shop_drawing": "shop drawing", "section": "section"}
        for name, value in artifacts.items():
            if name.endswith("_error"):
                label = _LABELS.get(name.removesuffix("_error"), name)
                parts.append(f"{label} skipped ({value})")
            else:
                label = _LABELS.get(name, name)
                parts.append(f"{label} {value}")
        print(" · ".join(parts))
        # The registry swallows a per-backend failure so one bad view can't kill the others — but a
        # FABRICATION file (STEP/IFC) that failed to write while the critic passed is a real failure the
        # exit code must report (else a script sees 0 and assumes the .step exists). Derived views (SVG/
        # section/shop drawing) failing stay non-fatal.
        from backends import fabrication as _fab
        fab_failed = sorted(n.removesuffix("_error") for n in artifacts
                            if n.endswith("_error") and n.removesuffix("_error") in {b.name for b in _fab()})
        if fab_failed:
            print(f"FABRICATION INCOMPLETE — {', '.join(fab_failed)} failed to export (critic passed, "
                  "but the fab file was not written)")
            return 1
        return 0
    print(f"\nwrote recipe {recipe} · STEP withheld — critic not all-pass (fabrication gate)")
    return 1


def edit_recipe(path: str, instruction: str, *, rounds: int = 1) -> int:
    """The --edit path: re-prompt an existing recipe into a MINIMAL diff, re-verify, re-export (S6)."""
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("cadquery not installed — editing needs the OCCT kernel (`pip install cadquery`).")
        return 1
    import difflib
    from pathlib import Path
    from agent.loop import edit
    from backends import step as step_backend

    p = Path(path)
    if not p.exists():
        print(f"no such recipe: {p}")
        return 1
    original = p.read_text()
    print(f"› editing {p}: {instruction}\n")
    res = edit(original, instruction, rounds=rounds)
    if res.ir is None:
        print(f"FAILED: {res.error}\n--- attempted program ---\n{res.program}")
        return 1

    diff = list(difflib.unified_diff(original.splitlines(), res.program.splitlines(), lineterm="", n=1))
    added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    print("--- diff ---")
    print("\n".join(diff) if diff else "(no change)")
    print(f"\nminimal diff: +{added} / -{removed} lines · {res.rounds} repair round(s)")

    p.write_text(res.program if res.program.endswith("\n") else res.program + "\n")
    if res.passed:
        sp = step_backend.compile(res.ir, p.parent)
        print(f"wrote {p} · STEP {sp}")
        return 0
    print(f"wrote {p} · STEP withheld — critic not all-pass")
    return 1


def plan_recipe(path: str, instruction: str, *, do_apply: bool = False) -> int:
    """--plan: propose a REVIEWABLE op-plan for a change to a recipe (prints the ops, writes nothing).
    --apply: build the plan (fab-gated — STEP only on an all-pass critic) + write the minimal diff.
    The model emits validated JSON ops we render, never code we exec() (R17)."""
    from pathlib import Path

    from agent import loop
    from agent.ops import summarize
    program = Path(path).read_text() if path and Path(path).exists() else ""
    plan = loop.plan(instruction, program=program)
    print(f"plan ({len(plan.ops)} op{'' if len(plan.ops) == 1 else 's'}):")
    for op in plan.ops:
        print(f"  · {summarize(op)}")
    if not do_apply:
        return 0

    from webapp.service import build_to_result
    out = Path("out")
    out.mkdir(exist_ok=True)
    res = build_to_result(program, plan, out=out)
    d = res.get("diff", {})
    if res.get("passed"):
        arts = " · ".join(f"{k} {v}" for k, v in res["artifacts"].items()
                          if k in ("step", "ifc", "dxf", "section-dxf"))
        print(f"applied · +{d.get('added', 0)}/−{d.get('removed', 0)} line(s) · {arts}")
        return 0
    print(f"NOT applied — critic not all-pass, STEP withheld · +{d.get('added', 0)}/−{d.get('removed', 0)} line(s)")
    return 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--eval" in argv:
        if "--repair" in argv and "--live" not in argv:
            print("note: --repair applies only to --live codegen; the reference-oracle eval ignores it.")
        return run_eval(live="--live" in argv, repair="--repair" in argv, via_mcp="--mcp" in argv)
    if "--mine-repairs" in argv:                      # A5: mine (failure→fix) pairs from the pool
        return mine_repairs(rounds=2)
    if "--serve" in argv:
        from webapp.server import serve
        port = 8765
        token = os.environ.get("LUDWIG_TOKEN") or None   # the embedding shell may pass one via env or --token
        for i, a in enumerate(argv):
            if a == "--serve" and i + 1 < len(argv) and argv[i + 1].isdigit():
                port = int(argv[i + 1])                   # back-compat: --serve <port>
            elif a == "--port" and i + 1 < len(argv):
                port = int(argv[i + 1])                   # --port <n> (0 = ephemeral, prints PORT=<chosen>)
            elif a == "--token" and i + 1 < len(argv):
                token = argv[i + 1]                       # loopback auth: require this token on /api/* + /out/*
            elif a == "--no-token":
                token = None                              # explicit open (the default)
        return serve(port, token=token)
    if argv and argv[0] == "mcp":   # `cli.py mcp` — the MCP server (S-MCP, A2), stdio transport
        from agent.mcp import main as mcp_main
        return mcp_main()

    # Parse --candidates N or --candidates=N (default 1). The space form consumes the NEXT token as its
    # value, so that index must be excluded from the positional args — else `--candidates 3 "prompt"`
    # leaks "3" into pos and compiles it as the prompt.
    candidates = 1
    consumed: set[int] = set()
    for i, arg in enumerate(argv):
        if arg.startswith("--candidates="):
            try:
                candidates = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg == "--candidates" and i + 1 < len(argv):
            try:
                candidates = int(argv[i + 1])
                consumed.add(i + 1)
            except ValueError:
                pass

    # v2 search knobs (WS2): --search opts into deliberative branch-and-prune; these flags override
    # ludwig.toml. Each accepts `--flag value` or `--flag=value`; the space form's value is consumed
    # so it doesn't leak into the positional prompt (same rule as --candidates).
    _SEARCH_FLAGS = {"--depth": "search.depth", "--branch": "search.branch",
                     "--keep-k": "search.keep_k", "--veri-ratio": "search.veri_ratio",
                     "--seed": "search.seed", "--budget-calls": "budget.max_calls"}
    overrides: dict[str, str] = {}
    for i, arg in enumerate(argv):
        key = arg.split("=", 1)[0]
        if key in _SEARCH_FLAGS:
            if "=" in arg:
                overrides[_SEARCH_FLAGS[key]] = arg.split("=", 1)[1]
            elif i + 1 < len(argv):
                overrides[_SEARCH_FLAGS[key]] = argv[i + 1]
                consumed.add(i + 1)

    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and i not in consumed]
    if "--plan" in argv or "--apply" in argv:   # reviewable op-plan (R17), routed before positional/--edit
        if len(pos) < 2:
            raise SystemExit('Usage: cli.py --plan <recipe.py> "<change>"  |  --apply <recipe.py> "<change>"')
        return plan_recipe(pos[0], pos[1], do_apply="--apply" in argv)
    if "--edit" in argv:
        if len(pos) < 2:
            raise SystemExit('Usage: cli.py --edit <recipe.py> "<change>"')
        return edit_recipe(pos[0], pos[1])
    if "--search" in argv:                      # WS2 deliberative branch-and-prune (opt-in)
        if not pos:
            raise SystemExit('Usage: cli.py "<prompt>" --search '
                             '[--depth D --branch B --keep-k K --veri-ratio R --budget-calls N --seed S]')
        from agent.config import load_config
        try:
            cfg = load_config(overrides=overrides)
        except (ValueError, KeyError) as e:
            raise SystemExit(f"config error: {e}")
        return compile_prompt(pos[0], search=True, cfg=cfg)
    if pos:
        return compile_prompt(pos[0], candidates=candidates)
    raise SystemExit(
        'Usage: cli.py "<prompt>" [--candidates N]  |  "<prompt>" --search [--depth D --branch B '
        '--veri-ratio R --budget-calls N]  |  --edit <recipe.py> "<change>"  |  '
        '--plan/--apply <recipe.py> "<change>"  |  --serve [port] [--port N] [--token T | --no-token]  |  '
        'mcp  |  --selftest  |  --eval [--live] [--repair] [--mcp]  |  --mine-repairs.'
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
