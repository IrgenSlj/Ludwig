"""BenchCAD edit-bench: foreign-program execution + the geometric grader (B1).

The task: given a real CadQuery program and a natural-language instruction ("Increase the cylinder
radius from 4.5 to 5.85"), produce the edited program. Graded geometrically against the ground-truth
solid — so a program that *looks* right but builds the wrong shape fails, which is the whole point.

Two numbers come out of a run:

- **normalized accuracy** — headroom-normalized IoU improvement, BenchCAD's edit metric:
  `(IoU(pred,gt) − IoU(orig,gt)) / (1 − IoU(orig,gt))`, clamped to [0,1]. 1.0 = landed the edit
  exactly; 0.0 = no better than leaving the program untouched. Published comparison: GPT-5.3
  (thinking) 0.865.
- **diff ratio** — our changed-line count over the ground-truth edit's changed-line count. This is
  the locked minimal-diff thesis (BRIEF §10: "a rewrite-on-edit is a bug") made measurable, and it
  is the number nobody else reports. ~1.0 is a surgical edit; ≫1 is a rewrite.

TRUST POSTURE — read before touching this module. Grading requires executing BenchCAD's programs,
which are third-party Python. `screen()` below is a **tripwire, not a sandbox**: it exists so that a
benchmark row doing something a geometry program has no business doing gets seen instead of silently
run. This whole path is developer-only — it is reachable from `cli.py --eval --bench` and nowhere
else, and MUST NOT become reachable from the daemon, the public demo, or MCP (BRIEF §10:
"a tool that emits fabrication files cannot execute untrusted code").
"""
from __future__ import annotations

import ast
import difflib
from typing import Any, Callable, Optional

from ir.elements import BRepHandle

# Modules a parametric-CAD program legitimately needs. Anything else trips the screen.
_ALLOWED_IMPORTS = frozenset({"cadquery", "cq", "math", "numpy", "np"})
# Names that have no place in a geometry program; their presence means the row deserves a look.
_BANNED_NAMES = frozenset({"__import__", "eval", "exec", "compile", "open", "input",
                           "globals", "locals", "vars", "getattr", "setattr", "delattr"})


class ScreenError(RuntimeError):
    """A benchmark program did something a geometry program has no business doing."""


def screen(code: str) -> None:
    """Refuse a program that imports outside the CAD allowlist or reaches for process/IO builtins.

    A tripwire, NOT a security boundary — do not treat a pass here as permission to run untrusted
    code anywhere else. For a well-formed geometry benchmark this should never fire; if it does,
    that is signal worth reading, not a bug to route around.
    """
    tree = ast.parse(code)                       # a syntax error propagates — that's a real failure
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _ALLOWED_IMPORTS:
                    raise ScreenError(f"disallowed import: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in _ALLOWED_IMPORTS:
                raise ScreenError(f"disallowed import-from: {node.module}")
        elif isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            raise ScreenError(f"disallowed name: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ScreenError(f"disallowed dunder attribute: {node.attr}")


def execute_foreign(code: str) -> tuple[Optional[BRepHandle], Optional[str]]:
    """Run a BenchCAD program and return (handle, error).

    BenchCAD programs follow the CQ-editor convention — assign `result`, then call
    `show_object(result)` — where `agent.loop.execute` requires an `element` of Ludwig's IR type.
    This adapter bridges that WITHOUT loosening the trusted-program rule in `agent.loop`: the two
    paths stay separate on purpose.

    The solid is materialized here so an OCCT `StdFail_NotDone` surfaces as a graded failure rather
    than exploding later inside the metric.
    """
    try:
        screen(code)
    except SyntaxError as e:
        return None, f"SyntaxError: {e}"
    except ScreenError as e:
        return None, f"ScreenError: {e}"

    import cadquery as cq

    captured: list[Any] = []
    ns: dict[str, Any] = {
        "cq": cq, "cadquery": cq,
        "show_object": lambda obj, *a, **k: captured.append(obj),
        "debug": lambda *a, **k: None,
        "log": lambda *a, **k: None,
    }
    try:
        exec(compile(code, "<benchcad>", "exec"), ns)     # noqa: S102 — see TRUST POSTURE above
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

    obj = captured[-1] if captured else ns.get("result")
    if obj is None:
        return None, "no result: program assigned neither `result` nor show_object(...)"
    try:
        wp = obj if isinstance(obj, cq.Workplane) else cq.Workplane().newObject(
            [obj] if not isinstance(obj, (list, tuple)) else list(obj))
        if wp.val().Volume() <= 0.0:
            return None, "empty solid: volume is zero"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    return BRepHandle(lambda: wp), None


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def diff_size(before: str, after: str, *, code_only: bool = True) -> int:
    """Changed lines between two programs (added + removed) — the minimal-diff instrument.

    Comments and blank lines are excluded by default, and that is load-bearing, not tidiness:
    **65% of edit-bench's ground-truth diff lines are comment-only** (measured over all 748 rows —
    the gt programs fill in a `# length = 92.8` parameter block the originals leave blank). Counting
    those would make any real edit look smaller than the reference for free, and would flatter
    Ludwig's minimal-diff claim on bookkeeping it never did. A comment is not a rewrite.
    """
    def lines(src: str) -> list[str]:
        out = src.splitlines()
        if not code_only:
            return out
        return [ln for ln in out if ln.strip() and not ln.strip().startswith("#")]

    return sum(1 for ln in difflib.unified_diff(lines(before), lines(after), n=0, lineterm="")
               if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")))


def normalized_accuracy(base_iou: float, pred_iou: float, *, eps: float = 1e-6) -> float:
    """Headroom-normalized improvement, clamped to [0,1].

    `base_iou` is IoU(orig, gt) — how close the UNEDITED program already is. When the edit barely
    moves the geometry there is no headroom to normalize by, so the score degenerates to a strict
    match on `pred_iou`; scoring 1.0 for "changed nothing" would be dishonest.
    """
    headroom = 1.0 - base_iou
    if headroom < eps:
        return 1.0 if pred_iou >= 1.0 - eps else 0.0
    return max(0.0, min(1.0, (pred_iou - base_iou) / headroom))


def grade(record: dict, pred_code: str, *, geom=None) -> dict:
    """Grade one prediction against the row's ground truth. Never raises — a failure is a result.

    Both IoUs are recomputed with our own exact-boolean metric rather than mixing in the dataset's
    stored voxel IoU, so the ratio is internally consistent. The stored value rides along as
    `iou_dataset` for cross-checking (docs/BENCH_PLAN.md).
    """
    from geometry import GeometryService
    from geometry.service import BooleanUnreliable

    g = geom or GeometryService()
    out = {
        "record_id": record["record_id"], "family": record["family"],
        "category": record.get("category"), "category_label": record.get("category_label"),
        "iou_dataset": record.get("iou"),
        "exec_ok": False, "ungradeable": None, "base_iou": None, "pred_iou": None, "score": 0.0,
        "diff_lines": diff_size(record["orig_code"], pred_code),
        "gt_diff_lines": diff_size(record["orig_code"], record["gt_code"]),
        "error": None,
    }
    # Reference solids first. If the DATASET's own programs don't build, or the kernel can't be
    # trusted on this geometry, the row is UNGRADEABLE — nothing a model produced could be scored
    # against it. Those rows leave the denominator entirely (and get counted out loud) instead of
    # depressing the number with failures no prediction could have avoided.
    orig, oerr = execute_foreign(record["orig_code"])
    gt, gerr = execute_foreign(record["gt_code"])
    if orig is None or gt is None:
        out["ungradeable"] = f"reference program failed to build: {oerr or gerr}"
        return out
    try:
        base = g.iou(orig, gt)
    except BooleanUnreliable as e:
        out["ungradeable"] = f"kernel unreliable on this geometry: {e}"
        return out

    pred, err = execute_foreign(pred_code)
    if pred is None:
        out["error"] = err                       # a real miss: the model's program doesn't build
        return out
    out["exec_ok"] = True
    try:
        pred_iou = g.iou(pred, gt)
    except BooleanUnreliable as e:
        out["ungradeable"] = f"kernel unreliable on this geometry: {e}"
        return out
    except Exception as e:
        out["error"] = f"iou failed: {type(e).__name__}: {e}"
        return out
    out["base_iou"], out["pred_iou"] = base, pred_iou
    out["score"] = normalized_accuracy(base, pred_iou)
    return out


def summarize(results: list[dict]) -> dict:
    """Aggregate a run.

    Ungradeable rows (the dataset's own program won't build, or OCCT can't be trusted on the
    geometry) are EXCLUDED from the denominator and reported as their own count — scoring them zero
    would blame the model for rows no prediction could have passed. `diff_ratio` is a median over
    graded rows: the mean is wrecked by the occasional rewrite, and the median is what actually says
    whether edits are typically surgical.
    """
    import statistics

    ungradeable = [r for r in results if r.get("ungradeable")]
    scored = [r for r in results if not r.get("ungradeable")]
    n = len(scored)
    graded = [r for r in scored if r["exec_ok"] and r["error"] is None]
    ratios = sorted(r["diff_lines"] / max(r["gt_diff_lines"], 1) for r in graded)
    exact = sum(1 for r in graded if r["score"] >= 0.999)
    return {
        "n": n,
        "ungradeable": len(ungradeable),
        "exec_rate": (sum(1 for r in scored if r["exec_ok"]) / n) if n else 0.0,
        "normalized_accuracy": (sum(r["score"] for r in scored) / n) if n else 0.0,
        "exact_rate": (exact / n) if n else 0.0,
        # A true median (mean of the two middle values on an even count) — `ratios[len//2]` was the
        # upper-middle, which reads high on exactly the even-n samples --bench-limit produces, and
        # this is the minimal-diff number we publish.
        "diff_ratio_median": (statistics.median(ratios) if ratios else 0.0),
        "families": len({r["family"] for r in scored}),
    }


# --------------------------------------------------------------------------- #
# predictors
# --------------------------------------------------------------------------- #

def predict_oracle(record: dict) -> str:
    """The ground truth itself. MUST grade 1.0 — this is how we validate the grader token-free."""
    return record["gt_code"]


def predict_noop(record: dict) -> str:
    """The unedited program. MUST grade 0.0 — the other half of the grader validation."""
    return record["orig_code"]


_EDIT_PROMPT = """You are editing a parametric CAD program written in CadQuery (Python).

Apply the requested change and return the FULL updated program. Change as little as possible —
keep every other line byte-for-byte identical. A rewrite is a failure even if the shape is right.

All units are millimetres. Keep the program's existing conventions (it assigns `result` and calls
`show_object(result)`; preserve that). Return ONLY the Python program — no prose, no fences.

## The program
{code}

## The change to make
{instruction}
"""

_REPAIR_SUFFIX = """

## Your previous attempt failed
{error}

Fix it. Return ONLY the corrected full program.
"""


def predict_live(record: dict, *, model: Optional[str] = None, rounds: int = 1) -> str:
    """Ludwig's edit path against a foreign program: one edit call, then deterministic repair.

    The repair signal is what the deterministic critic gives for FREE on geometry we did not author
    — the program failed to execute, or OCCT reports the solid invalid. The ground truth is never
    consulted here (that would be training on test), so `rounds > 0` is an honest test of the
    thesis: a deterministic verifier closes the gap one-shot generation leaves open.
    """
    from agent import inference
    from agent.loop import _strip_fences, _tier_model
    from geometry import GeometryService

    model = model or _tier_model("critic")       # editing is best-tier reasoning (BRIEF §5), as agent.loop.edit
    prompt = _EDIT_PROMPT.format(code=record["orig_code"], instruction=record["instruction"])
    code = _strip_fences(inference.infer(prompt, model=model))
    g = GeometryService()
    for _ in range(max(0, rounds)):
        handle, err = execute_foreign(code)
        if handle is not None:
            try:
                if g.is_valid(handle):
                    break
                err = "OCCT reports the solid invalid (non-manifold / not watertight / self-intersecting)"
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
        code = _strip_fences(inference.infer(prompt + _REPAIR_SUFFIX.format(error=err), model=model))
    return code


def by_category(results: list[dict]) -> list[dict]:
    """Per-edit-category breakdown, worst first — the B4 capability to-do list.

    BenchCAD labels every row with the KIND of edit it asks for (`literal_replace`, and harder
    categories above it). Aggregating the score by that label is what turns a single headline number
    into a ranked list of what Ludwig can't yet do — the same mechanism that moved the frozen-set
    number 60→93 by naming the missing op rather than by tuning the prompt (FINDINGS).
    """
    buckets: dict[tuple, list[dict]] = {}
    for r in results:
        if r.get("ungradeable"):
            continue
        buckets.setdefault((r.get("category") or "?", r.get("category_label") or "?"), []).append(r)
    rows = [
        {"category": cat, "label": label, "n": len(rs),
         "score": sum(x["score"] for x in rs) / len(rs),
         "exec_rate": sum(1 for x in rs if x["exec_ok"]) / len(rs),
         "exact": sum(1 for x in rs if x["score"] >= 0.999)}
        for (cat, label), rs in buckets.items()
    ]
    return sorted(rows, key=lambda d: (d["score"], -d["n"]))


def run(rows: list[dict], predict: Callable[[dict], str], *,
        on_row: Optional[Callable[[dict], None]] = None) -> tuple[dict, list[dict]]:
    """Grade every row with `predict`. Returns (summary, results). A predictor that raises is a fail."""
    from geometry import GeometryService

    g = GeometryService()
    results: list[dict] = []
    for row in rows:
        try:
            pred = predict(row)
            res = grade(row, pred, geom=g)
        except Exception as e:
            res = {"record_id": row["record_id"], "family": row["family"],
                   "category": row.get("category"), "category_label": row.get("category_label"),
                   "iou_dataset": row.get("iou"), "exec_ok": False, "ungradeable": None,
                   "base_iou": None, "pred_iou": None, "score": 0.0, "diff_lines": 0,
                   "gt_diff_lines": diff_size(row["orig_code"], row["gt_code"]),
                   "error": f"predictor raised: {type(e).__name__}: {e}"}
        results.append(res)
        if on_row:
            on_row(res)
    return summarize(results), results
