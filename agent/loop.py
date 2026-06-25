"""The agentic loop — the compiler driver (BRIEF §5).

    prompt → codegen (LLM writes a program against CadQuery + the thin element-API)
           → execute (build the IR)
           → VERIFY (critic over the IR)
           → if fail: feed failures back → repair (fix only failures, keep intent) → re-verify
           → if pass: (select / compile backends — S5+)

S3 wires generate + execute + repair on the live provider-blind inference seam. The `verify` here is
PROVISIONAL — a minimal geometric/dimensional check so the loop closes and repair has a signal; the
real deterministic critic PANEL (semantic checks, registry, aggregation) is S4 and will replace it
without touching this loop (BRIEF §0 gate). Heavy kernel use stays inside execute() (lazy).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent import inference
from critic.base import CheckResult, Critique, Status
from ir.elements import Element

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class Brief:
    """The locked intent a candidate is generated and graded against."""
    prompt: str
    named_dims: dict[str, float] = field(default_factory=dict)   # declared dims the critic enforces
    holes: Optional[int] = None                                  # None = unknown (bare prompt); skip the check
    units: str = "mm"

    @classmethod
    def from_dict(cls, d: dict) -> "Brief":
        return cls(prompt=d["prompt"], named_dims=dict(d.get("dims", {})),
                   holes=(int(d["holes"]) if "holes" in d else None))


@dataclass
class LoopResult:
    program: str
    ir: Optional[Element]
    critique: Optional[Critique]
    passed: bool
    rounds: int
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# prompt assembly (a minimal stack; the composable file-driven stack is later)
# --------------------------------------------------------------------------- #

def _read(name: str) -> str:
    return (_PROMPTS / name).read_text()


def _api_and_standards() -> str:
    from toolkit import standards
    clear = standards.load()["clearance_holes_mm"]
    return (
        "## The element API you call (assign your final Part to a variable named `element`)\n"
        "- box(id, length, width, height) -> Element   # extents registered as named dims length/width/height\n"
        "- hole(element, diameter, (x, y))             # through-hole; (x, y) from the top-face centre, mm\n"
        f"- clearance_hole(element, \"M8\", (x, y))       # diameter from standards (M8 -> ⌀{clear['M8']}), never guessed\n"
        "- raw CadQuery is available as `cq`; assign solids to element.geometry and call "
        "element.register_dim(name, value)\n"
        "All units mm. Do not print; just build `element`.\n\n"
        f"## Standards — clearance holes (mm)\n{clear}\n"
    )


def _codegen_prompt(brief: Brief) -> str:
    holes = "" if brief.holes is None else f"\nHoles expected: {brief.holes}"
    dims = f"\nDeclared dimensions (exact, mm): {brief.named_dims}" if brief.named_dims else ""
    return (
        f"{_read('codegen.md')}\n\n{_api_and_standards()}\n"
        f"## Brief\n{brief.prompt}{dims}{holes}\n\n"
        "Return ONLY the Python program — no prose, no markdown fences."
    )


def _repair_prompt(program: str, brief: Brief, critique: Optional[Critique], err: Optional[str]) -> str:
    if err:
        issues = err
    elif critique:
        issues = "; ".join(f"{c.check}: {c.message}" for c in critique.failures) or "unspecified"
    else:
        issues = "unspecified"
    return (
        f"{_read('repair.md')}\n\n{_api_and_standards()}\n"
        f"## The program\n{program}\n\n"
        f"## Critic failures — fix ONLY these, keep everything that passes\n{issues}\n\n"
        f"## Brief (unchanged intent)\n{brief.prompt} | dims {brief.named_dims} | holes {brief.holes}\n\n"
        "Return ONLY the full corrected Python program — no prose, no fences."
    )


# --------------------------------------------------------------------------- #
# execute + verify
# --------------------------------------------------------------------------- #

def _strip_fences(src: str) -> str:
    src = src.strip()
    if src.startswith("```"):
        src = re.sub(r"^```[A-Za-z0-9]*[ \t]*\n?", "", src)
        src = re.sub(r"\n?```$", "", src)
    return src.strip()


def execute(program: str) -> tuple[Optional[Element], Optional[str]]:
    """Run a generated program in a toolkit namespace; return (element, error).

    The program is design-as-code — running it IS the compile step (as the mesh era exec'd bpy).
    Forces the lazy geometry to build so OCCT `StdFail_NotDone` surfaces here and feeds repair (§8).
    """
    import cadquery
    import toolkit
    from toolkit import standards

    ns = {
        "cq": cadquery, "cadquery": cadquery, "standards": standards, "Element": Element,
        "part": toolkit.part, "box": toolkit.box, "hole": toolkit.hole,
        "clearance_hole": toolkit.clearance_hole,
    }
    try:
        exec(compile(_strip_fences(program), "<ludwig-program>", "exec"), ns)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    el = ns.get("element")
    if not isinstance(el, Element):
        return None, "program did not assign an Element to `element`"
    try:
        if el.geometry is not None:
            el.geometry.solid()        # force the build now → surface kernel errors
    except Exception as e:
        return None, f"geometry build failed: {type(e).__name__}: {e}"
    return el, None


def verify(el: Element, brief: Brief) -> Critique:
    """PROVISIONAL geometric/dimensional verifier (S3). Replaced by the critic panel in S4."""
    from geometry import GeometryService
    from toolkit.standards import bbox_gate

    g = GeometryService()
    tol = bbox_gate()
    checks: list[CheckResult] = []
    length, width, height = g.bbox(el.geometry)
    built = {"length": length, "width": width, "height": height}
    for name, want in brief.named_dims.items():
        have = built.get(name)
        ok = have is not None and abs(have - want) <= tol
        checks.append(CheckResult(f"dim:{name}", Status.PASS if ok else Status.FAIL,
                                  "" if ok else f"declared {want}, built {have}", el.id))
    if brief.holes is not None:
        n = g.cylindrical_face_count(el.geometry)
        checks.append(CheckResult("hole_count", Status.PASS if n == brief.holes else Status.FAIL,
                                  "" if n == brief.holes else f"declared {brief.holes}, built {n}", el.id))
    checks.append(CheckResult("solid_valid",
                              Status.PASS if g.is_valid(el.geometry) else Status.FAIL, "", el.id))
    return Critique(checks=checks)


# --------------------------------------------------------------------------- #
# generate + run
# --------------------------------------------------------------------------- #

def generate(brief: Brief, *, model: Optional[str] = None) -> str:
    """One codegen call (cheap tier). The provider is whatever CLI is on PATH (seam-blind)."""
    return _strip_fences(inference.infer(_codegen_prompt(brief), model=model))


def first_pass(brief: Brief, *, model: Optional[str] = None):
    """Generate ONCE and execute — no repair. This is what the [H6] pass-rate measures."""
    program = generate(brief, model=model)
    el, err = execute(program)
    return program, el, err


def run(brief: Brief, *, rounds: int = 2, model: Optional[str] = None) -> LoopResult:
    """Generate → execute → verify → repair until pass or rounds exhausted."""
    program = generate(brief, model=model)
    el, err = execute(program)
    crit = verify(el, brief) if el is not None else None
    rnd = 0
    while rnd < rounds and (el is None or not crit.passed):
        program = _strip_fences(inference.infer(_repair_prompt(program, brief, crit, err), model=model))
        el, err = execute(program)
        crit = verify(el, brief) if el is not None else None
        rnd += 1
    passed = el is not None and crit is not None and crit.passed
    return LoopResult(program, el, crit, passed, rnd, err)


__all__ = ["Brief", "LoopResult", "execute", "verify", "generate", "first_pass", "run"]
