"""The agentic loop — the compiler driver (BRIEF §5).

    prompt → codegen (LLM writes a program against CadQuery + the thin element-API)
           → execute (build the IR)
           → VERIFY (critic over the IR)
           → if fail: feed failures back → repair (fix only failures, keep intent) → re-verify
           → if pass: (select / compile backends — S5+)

Model tiering (BRIEF §5): codegen uses the CHEAP model tier; repair uses the BEST model tier.
Tier names are read from standards.yaml: inference.codegen_tier / inference.critic_tier.
Override with `model=` to pass a specific model name.

Brief extraction: when a Brief has no named_dims or holes set explicitly, the loop attempts
to parse them from the prompt text so the inline compile path (`cli.py "<prompt>"`) gets
proper critic coverage instead of vacuum-passing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent import inference
from agent.errors import GeometryBuildError, MissingElementError, SyntaxError_
from critic.base import Critique, Severity
from ir.elements import Element

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

# Regex patterns for extracting declared dims and hole counts from a free-text prompt.
# These are lightweight heuristics — they don't need to be perfect, just good enough to
# give the inline compile path non-vacuum critic coverage. The dim pattern captures the common
# "A × B × C" extent triple (× or x separators, ints or decimals) so a bare-prompt live compile
# is dimensionally verified, not just geometrically — the headline critic promise (BRIEF §6).
_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:×|x)\s*(\d+(?:\.\d+)?)\s*(?:×|x)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_HOLES_RE = re.compile(
    r"(two|three|four|five|six|seven|eight|nine|ten)\s+(?:\S+\s+){0,2}?holes?", re.IGNORECASE)
# The count digit must NOT be a thread size: a letter before it (the M in "M8") disqualifies it,
# so "two M8 holes" reads 2 (via the word pattern), never 8.
_HOLES_DIGIT_RE = re.compile(r"(?<![A-Za-z])(\d+)\s+(?:M\d+\s+)?holes?", re.IGNORECASE)
_WORD_NUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _extract_dims(prompt: str) -> dict[str, float]:
    """Try to extract approximate named dims from a free-text prompt.

    Matches patterns like "80 × 40 × 6 mm" and returns {length, width, height}.
    This is intentionally imprecise — the critic will catch wrong values.
    """
    m = _DIM_RE.search(prompt)
    if m:
        a, b, c = (float(x) for x in m.groups())
        return {"length": a, "width": b, "height": c}
    return {}


def _extract_holes(prompt: str) -> Optional[int]:
    """Try to extract a hole count from a free-text prompt.

    Matches "two M8 holes", "4 holes", "no holes" etc.
    Returns None if uncertain.
    """
    if "no holes" in prompt.lower():
        return 0
    m = _HOLES_DIGIT_RE.search(prompt)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m = _HOLES_RE.search(prompt)
    if m:
        word = m.group(1).lower()
        return _WORD_NUM.get(word)
    return None


def _tier_model(tier: str) -> Optional[str]:
    """Resolve a tier ('codegen' or 'critic') to a concrete model name via standards.yaml.

    `inference.{codegen,critic}_tier` names a tier LABEL ('cheap' / 'best'); `inference.tiers` maps
    that label to a real model the provider accepts (e.g. cheap -> haiku). An unmapped label — or
    'default' — resolves to None (the provider's default model), NEVER the literal label, which the
    CLI rejects ("model 'cheap' may not exist"). This is the seam BRIEF §5 model-tiering rides on.
    """
    try:
        from toolkit.standards import load
        cfg = load().get("inference", {})
        label = cfg.get(f"{tier}_tier", "default")
        if not label or label == "default":
            return None
        model = (cfg.get("tiers", {}) or {}).get(label)   # label MUST be defined in tiers: else default
        return model or None
    except Exception:
        return None


@dataclass
class Brief:
    """The locked intent a candidate is generated and graded against."""
    prompt: str
    named_dims: dict[str, float] = field(default_factory=dict)   # declared dims the critic enforces
    holes: Optional[int] = None                                  # None = unknown (bare prompt); skip the check
    units: str = "mm"
    use_class: Optional[str] = None     # AD-K stair use class (private/general/institutional); compliance critic

    def __post_init__(self) -> None:
        # Auto-extract dims and holes from the prompt if not explicitly provided.
        # This gives the inline compile path proper critic coverage.
        if not self.named_dims:
            extracted = _extract_dims(self.prompt)
            if extracted:
                self.named_dims = extracted
        if self.holes is None:
            extracted = _extract_holes(self.prompt)
            if extracted is not None:
                self.holes = extracted

    @classmethod
    def from_dict(cls, d: dict) -> "Brief":
        return cls(prompt=d["prompt"], named_dims=dict(d.get("dims", {})),
                   holes=(int(d["holes"]) if "holes" in d else None),
                   use_class=d.get("use_class"))


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
        "- place(element, (dx, dy, dz))                # move a part by an offset in mm (for assemblies)\n"
        "- stack(base, top)                            # seat `top` on the +z face of `base` (both centred)\n"
        "- assembly(id, *children) -> Element          # compose built Elements into a compound Assembly\n"
        "  e.g. base=box('b',60,60,10); top=box('t',40,40,10); stack(base, top); "
        "element=assembly('asm', base, top)\n"
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
    """Extract the program from a model reply. Prefer a fenced ```code``` block wherever it appears
    (models sometimes wrap the program in prose despite instructions); fall back to the raw text."""
    src = src.strip()
    block = re.search(r"```[A-Za-z0-9]*[ \t]*\n(.*?)\n?```", src, re.DOTALL)
    if block:
        return block.group(1).strip()
    if src.startswith("```"):                       # an unterminated fence
        src = re.sub(r"^```[A-Za-z0-9]*[ \t]*\n?", "", src)
    return src.strip()


def execute(program: str, *, record: bool = False) -> tuple[Optional[Element], Optional[str]]:
    """Run a generated program in a toolkit namespace; return (element, error).

    The program is design-as-code — running it IS the compile step (as the mesh era exec'd bpy).
    Forces the lazy geometry to build so OCCT `StdFail_NotDone` surfaces here and feeds repair (§8).
    `record=True` runs it under toolkit.recording() so the returned Element carries a FeatureGraph
    (el.graph) for the deterministic evaluator — additive, the closure geometry path is unchanged ([H1]).
    """
    import cadquery
    import toolkit
    from toolkit import standards

    ns = {
        "cq": cadquery, "cadquery": cadquery, "standards": standards, "Element": Element,
        "part": toolkit.part, "box": toolkit.box, "hole": toolkit.hole,
        "clearance_hole": toolkit.clearance_hole, "panel": toolkit.panel, "anchor": toolkit.anchor,
        "assembly": toolkit.assembly, "place": toolkit.place, "stack": toolkit.stack,
        "profile": toolkit.profile, "stair": toolkit.stair, "wall": toolkit.wall,
        "opening": toolkit.opening, "sketch": toolkit.sketch, "extrude": toolkit.extrude,
    }
    try:
        src = compile(_strip_fences(program), "<ludwig-program>", "exec")
        if record:
            from toolkit.elements import recording
            with recording():
                exec(src, ns)
        else:
            exec(src, ns)
    except SyntaxError as e:
        return None, f"{SyntaxError_.__name__}: {e}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    el = ns.get("element")
    if not isinstance(el, Element):
        return None, f"{MissingElementError.__name__}: program did not assign an Element to `element`"
    try:
        if el.geometry is not None:
            el.geometry.solid()        # force the build now → surface kernel errors
    except Exception as e:
        op = "hole" if "hole" in str(e).lower() else "fillet" if "fillet" in str(e).lower() else "unknown"
        return None, f"{GeometryBuildError.__name__}: {type(e).__name__}: {e} (op={op})"
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
    """One codegen call (CHEAP tier by default). The provider is whatever CLI is on PATH."""
    return _strip_fences(inference.infer(_codegen_prompt(brief), model=model or _tier_model("codegen")))


def first_pass(brief: Brief, *, model: Optional[str] = None):
    """Generate ONCE and execute — no repair. This is what the [H6] pass-rate measures."""
    program = generate(brief, model=model)
    el, err = execute(program)
    return program, el, err


def _weighted_failures(crit: Optional[Critique]) -> tuple:
    """Rank candidates by severity-weighted failure count.

    Returns a tuple (is_build_failure, weighted_score) where lower is better.
    CRITICAL failures count as 100 each, ERROR as 10, WARNING as 1.
    A build failure (el is None) is always worst: (1, 0).
    """
    if crit is None:
        return (1, 0)
    score = 0
    for c in crit.failures:
        sev = getattr(c, "severity", Severity.ERROR)
        if sev == Severity.CRITICAL:
            score += 100
        elif sev == Severity.WARNING:
            score += 1
        else:
            score += 10
    return (0, score)


def run(brief: Brief, *, candidates: int = 1, rounds: int = 2, model: Optional[str] = None,
        on_event=None) -> LoopResult:
    """Generate → execute → verify → repair until pass or rounds exhausted.

    Codegen uses the CHEAP model tier; repair uses the BEST model tier (BRIEF §5).
    When `candidates` > 1, generates that many first-pass attempts and selects the best by
    severity-weighted deterministic critic. A true pairwise aesthetic judge among passing
    candidates is deferred — it needs the render backend.

    `on_event(dict)` is an optional progress callback the compiler driver fires at each stage
    (codegen / execute / critic / select / repair) so a frontend can paint a live Activity Rail
    (UX_BRIEF §Activity Rail). It never changes behavior — when None, this is the original loop.
    """
    def emit(**ev):
        if on_event:
            try:
                on_event(ev)
            except Exception:
                pass

    codegen_model = model or _tier_model("codegen")
    critic_model = model or _tier_model("critic")

    attempts = []
    for i in range(candidates):
        emit(stage="codegen", status="running", candidate=i + 1, candidates=candidates)
        program = generate(brief, model=codegen_model)
        emit(stage="codegen", status="done", candidate=i + 1, candidates=candidates)
        emit(stage="execute", status="running", candidate=i + 1, candidates=candidates)
        el, err = execute(program)
        emit(stage="execute", status="failed" if err else "done", candidate=i + 1,
             candidates=candidates, message=err)
        crit = None
        if el is not None:
            emit(stage="critic", status="running", candidate=i + 1, candidates=candidates)
            crit = verify(el, brief)
            emit(stage="critic", status="done", candidate=i + 1, candidates=candidates,
                 checks=len(crit.checks), passed=crit.passed)
        attempts.append((program, el, crit, err))

    program, el, crit, err = min(attempts, key=lambda a: _weighted_failures(a[2]))
    if candidates > 1:
        emit(stage="select", status="done", candidates=candidates,
             passed=(crit.passed if crit else False))

    rnd = 0
    while rnd < rounds and (el is None or not crit.passed):
        emit(stage="repair", status="running", round=rnd + 1)
        program = _strip_fences(inference.infer(_repair_prompt(program, brief, crit, err), model=critic_model))
        el, err = execute(program)
        crit = verify(el, brief) if el is not None else None
        emit(stage="repair", status="done", round=rnd + 1,
             passed=(crit.passed if crit else False), message=err)
        rnd += 1
    passed = el is not None and crit is not None and crit.passed
    return LoopResult(program, el, crit, passed, rnd, err)


def edit(program: str, instruction: str, *, brief: Optional[Brief] = None,
         rounds: int = 1, model: Optional[str] = None) -> LoopResult:
    """Re-prompt an existing program with a change, aiming for a MINIMAL diff (the editability thesis).

    References are by program lineage, not kernel handle ([H2]): the edit rewrites the *program text*
    and re-executes; nothing points into a stale B-rep.
    Repair uses the BEST model tier.
    """
    b = brief or Brief(prompt=instruction)
    critic_model = model or _tier_model("critic")
    new = _strip_fences(inference.infer(_edit_prompt(program, instruction), model=model))
    el, err = execute(new)
    crit = verify(el, b) if el is not None else None
    rnd = 0
    while rnd < rounds and (el is None or not crit.passed):
        new = _strip_fences(inference.infer(_repair_prompt(new, b, crit, err), model=critic_model))
        el, err = execute(new)
        crit = verify(el, b) if el is not None else None
        rnd += 1
    passed = el is not None and crit is not None and crit.passed
    return LoopResult(new, el, crit, passed, rnd, err)


__all__ = ["Brief", "LoopResult", "execute", "verify", "generate", "first_pass", "run", "edit"]
