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

    ok = all(passed for _, passed, _ in checks)
    for label, passed, detail in checks:
        mark = "ok  " if passed else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail and not passed else ""))
    print(("PASS" if ok else "FAIL") + f" — {sum(p for _, p, _ in checks)}/{len(checks)} checks")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    raise SystemExit(
        "compile/--edit land in P0 (S3 codegen, S6 edit). Run `python3 cli.py --selftest`. See BRIEF.md."
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
