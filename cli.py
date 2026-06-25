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


def compile_prompt(prompt: str, *, rounds: int = 2) -> int:
    """The compile path: prompt → generated program → executed IR (BRIEF §5, S3 gate)."""
    try:
        import cadquery  # noqa: F401
    except ImportError:
        print("cadquery not installed — compiling needs the OCCT kernel (`pip install cadquery`).")
        return 1
    from agent.loop import Brief, run
    from geometry import GeometryService

    print(f"› compiling: {prompt}\n")
    res = run(Brief(prompt=prompt), rounds=rounds)
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

    # Persist the recipe (the source of truth) and, if the critic passed, the STEP deliverable.
    from pathlib import Path
    from backends import step as step_backend
    out = Path("out")
    out.mkdir(exist_ok=True)
    recipe = out / f"{res.ir.id}.py"
    recipe.write_text(res.program + "\n")
    if res.passed:  # pre-export validation hook (BRIEF §5): no fabrication file leaves on a failing critic
        step_path = step_backend.compile(res.ir, out)
        print(f"\nwrote recipe {recipe} · STEP {step_path}")
        return 0
    print(f"\nwrote recipe {recipe} · STEP withheld — critic not all-pass (fabrication gate)")
    return 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--eval" in argv:
        return run_eval(live="--live" in argv, repair="--repair" in argv)
    prompts = [a for a in argv if not a.startswith("--")]
    if prompts:
        return compile_prompt(prompts[0])
    raise SystemExit(
        'Usage: cli.py "<prompt>"  |  --selftest  |  --eval [--live]  |  --edit (S6). See BRIEF.md.'
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
