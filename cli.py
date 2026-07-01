#!/usr/bin/env python3
"""Ludwig CLI — the headless entry point (BRIEF §7).

  python3 cli.py "a steel bracket, 80x40x6mm, two M8 holes"   # P0/S3+ — compile a model
  python3 cli.py --edit <path> "make the holes M10"           # P0/S6 — minimal-diff re-prompt
  python3 cli.py --selftest                                   # the regression gate (no LLM tokens)

--selftest is the gate that stays green at every phase. Today it exercises the pure-Python IR
spine (no kernel, no inference); it grows a real OCCT build once the geometry service lands (S2/S5).
"""
from __future__ import annotations

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

    ok = all(passed for _, passed, _ in checks)
    for label, passed, detail in checks:
        mark = "ok  " if passed else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail and not passed else ""))
    print(("PASS" if ok else "FAIL") + f" — {sum(p for _, p, _ in checks)}/{len(checks)} checks")
    return 0 if ok else 1


def run_eval(*, live: bool = False, repair: bool = False) -> int:
    """First-pass geometric pass-rate over the frozen held-out brief set ([H6]).

    Default uses the deterministic reference oracle (no tokens). `--live` swaps in real LLM codegen;
    `--live --repair` measures the post-repair rate (the full loop + critic panel) — the number that
    reflects what the loop actually ships.
    """
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("cadquery not installed — the eval harness needs the OCCT kernel "
              "(`pip install cadquery`). See BRIEF.md §4.")
        return 1
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


def compile_prompt(prompt: str, *, candidates: int = 1, rounds: int = 2) -> int:
    """The compile path: prompt → generated program → executed IR (BRIEF §5, S3 gate)."""
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("cadquery not installed — compiling needs the OCCT kernel (`pip install cadquery`).")
        return 1
    from agent.loop import Brief, run
    from geometry import GeometryService

    print(f"› compiling: {prompt}\n")
    res = run(Brief(prompt=prompt), candidates=candidates, rounds=rounds)
    print("--- program ---")
    print(res.program)
    print("\n--- result ---")
    if res.ir is None:
        print(f"FAILED to build an Element: {res.error}")
        return 1
    length, width, height = GeometryService().bbox(res.ir.geometry) if res.ir.geometry else (0.0, 0.0, 0.0)
    print(f"built {res.ir.id!r}: bbox {length:.3f}×{width:.3f}×{height:.3f} mm · "
          f"{len(res.ir.manifest)} named dims · {res.rounds} repair round(s)")
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
                   "shop_drawing": "shop drawing", "section": "section", "render": "render"}
        for name, value in artifacts.items():
            if name.endswith("_error"):
                label = _LABELS.get(name.removesuffix("_error"), name)
                parts.append(f"{label} skipped ({value})")
            else:
                label = _LABELS.get(name, name)
                parts.append(f"{label} {value}")
        print(" · ".join(parts))
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


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--eval" in argv:
        return run_eval(live="--live" in argv, repair="--repair" in argv)
    if "--serve" in argv:
        from webapp.server import serve
        port = 8765
        for i, a in enumerate(argv):
            if a == "--serve" and i + 1 < len(argv) and argv[i + 1].isdigit():
                port = int(argv[i + 1])
        return serve(port)

    # Parse --candidates N or --candidates=N (default 1)
    candidates = 1
    for i, arg in enumerate(argv):
        if arg.startswith("--candidates="):
            try:
                candidates = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg == "--candidates" and i + 1 < len(argv):
            try:
                candidates = int(argv[i + 1])
            except ValueError:
                pass

    pos = [a for a in argv if not a.startswith("--")]
    if "--edit" in argv:
        if len(pos) < 2:
            raise SystemExit('Usage: cli.py --edit <recipe.py> "<change>"')
        return edit_recipe(pos[0], pos[1])
    if pos:
        return compile_prompt(pos[0], candidates=candidates)
    raise SystemExit(
        'Usage: cli.py "<prompt>" [--candidates N]  |  --edit <recipe.py> "<change>"  |  --serve [port]  |  --selftest  |  --eval [--live] [--repair].'
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
