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
from critic.base import Critique
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
        "- panel(id, length, height, thickness) -> Element   # a precast wall panel (type 'Panel')\n"
        "- anchor(element, diameter, (x, y), depth)    # a cast-in blind pocket in the top (+z) edge\n"
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


def _edit_prompt(program: str, instruction: str) -> str:
    return (
        f"{_read('edit.md')}\n\n{_api_and_standards()}\n"
        f"## The current program\n{program}\n\n"
        f"## The change to make\n{instruction}\n\n"
        "Return ONLY the full updated Python program — change as little as possible; keep every other "
        "line byte-for-byte identical. No prose, no fences."
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
        "clearance_hole": toolkit.clearance_hole, "panel": toolkit.panel, "anchor": toolkit.anchor,
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
    """Run the deterministic critic PANEL (BRIEF §6). The loop is panel-agnostic — adding a critic
    is `critic.panel.register(...)`, never a change here (BRIEF §0 gate / [H4])."""
    from critic import panel
    return panel.evaluate(el, brief)


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


def edit(program: str, instruction: str, *, brief: Optional[Brief] = None,
         rounds: int = 1, model: Optional[str] = None) -> LoopResult:
    """Re-prompt an existing program with a change, aiming for a MINIMAL diff (the editability thesis).

    References are by program lineage, not kernel handle ([H2]): the edit rewrites the *program text*
    and re-executes; nothing points into a stale B-rep.
    """
    b = brief or Brief(prompt=instruction)
    new = _strip_fences(inference.infer(_edit_prompt(program, instruction), model=model))
    el, err = execute(new)
    crit = verify(el, b) if el is not None else None
    rnd = 0
    while rnd < rounds and (el is None or not crit.passed):
        new = _strip_fences(inference.infer(_repair_prompt(new, b, crit, err), model=model))
        el, err = execute(new)
        crit = verify(el, b) if el is not None else None
        rnd += 1
    passed = el is not None and crit is not None and crit.passed
    return LoopResult(new, el, crit, passed, rnd, err)


__all__ = ["Brief", "LoopResult", "execute", "verify", "generate", "first_pass", "run", "edit"]
