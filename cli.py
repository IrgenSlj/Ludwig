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
    from ir.feature import FeatureGraph, FeatureNode
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
                   "shop_drawing": "shop drawing", "render": "render"}
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
