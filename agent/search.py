"""Deliberative branch-and-prune search (WS2, docs/V2_ROADMAP.md §2).

The v1 loop is a degenerate search tree: `candidates` fresh proposals once, then linear repair of the
single best. BlenderGym's result (RESEARCH_NOTES §1): a d×b propose–verify–improve tree, verifier-pruned,
beats linear at equal compute, and verifier compute dominates at scale. **Ludwig's edge:** its verifier is
the *deterministic* critic — free and exact — so pruning costs zero model calls and we can prune hard.

This module is the substrate-agnostic driver. It touches **no** model or kernel directly: `propose`,
`refine`, `execute`, `verify`, and `score` are injected, so the whole tree is exercised token-free with a
scripted mock (tests) and bound to the real loop in `agent.loop.run_search`. Score is a total order where
**lower is better** (e.g. `agent.loop._weighted_failures`: a passing critique is the minimum, a build
failure the maximum).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


def plan_levels(depth: int, branch: int, veri_ratio: float,
                max_calls: Optional[int] = None) -> list[int]:
    """Proposals to attempt per tree level: index 0 = explore (fresh), 1..d-1 = refine (improve).

    Without a binding `max_calls`, every level gets `branch` (the ideal d×b shape). When the call ceiling
    binds, split it into an **explore share** (level 0) and a **refine share** (deeper levels) by
    `veri_ratio`: the refine share is `veri_ratio` of the budget, explore the rest. Each level is capped
    at `branch`; trailing empty levels are dropped. Because Ludwig's verification is free, `veri_ratio`
    tunes explore-vs-refine spend (not generate-vs-judge) and is inert unless the ceiling binds — matching
    the BlenderGym finding that the optimal verification share rises with budget (RESEARCH_NOTES §1).

    Pure function — no model calls; unit-tested directly.
    """
    if depth < 1 or branch < 1:
        raise ValueError(f"depth and branch must be >= 1, got depth={depth} branch={branch}")
    ideal = [branch] * depth
    if max_calls is None or sum(ideal) <= max_calls:
        return ideal
    explore = min(branch, max(1, round(max_calls * (1.0 - veri_ratio))))
    refine_total = max_calls - explore
    levels = [explore]
    for _ in range(depth - 1):
        if refine_total <= 0:
            break
        take = min(branch, refine_total)
        levels.append(take)
        refine_total -= take
    return levels


@dataclass
class Candidate:
    """One node in the search tree — a program and how the deterministic critic scored it."""
    branch_id: str
    program: str
    ir: Any = None
    critique: Any = None
    err: Optional[str] = None
    score: tuple = ()
    level: int = 0
    parent_id: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.ir is not None and self.critique is not None and bool(self.critique.passed)


@dataclass
class SearchResult:
    """The best branch found, plus the search bookkeeping needed for telemetry (WS7) and eval."""
    best: Optional[Candidate]
    calls_used: int
    reason: str                       # converged | budget | exhausted
    levels: list[int] = field(default_factory=list)
    nodes: int = 0

    @property
    def passed(self) -> bool:
        return bool(self.best and self.best.passed)


def _emit(on_event, **ev) -> None:
    if on_event:
        try:
            on_event(ev)
        except Exception:
            pass


def search(brief: Any, *, depth: int, branch: int, keep_k: int, veri_ratio: float,
           propose: Callable[[Any], str],
           refine: Callable[[Candidate, Any], str],
           execute: Callable[[str], tuple[Any, Optional[str]]],
           verify: Callable[[Any, Any], Any],
           score: Callable[[Any], tuple],
           max_calls: Optional[int] = None,
           on_event: Optional[Callable[[dict], None]] = None) -> SearchResult:
    """Run the d×b branch-and-prune search and return the best branch.

    Per level: generate proposals (fresh from `brief` at level 0; `refine` of a survivor at deeper levels,
    round-robin across the current beam), execute + verify + `score` each, then keep the top-`keep_k` of
    {new children} ∪ {current survivors} — so the beam is monotonic and never discards the best seen. Stops
    early when the best survivor passes the critic (`converged`); stops when the plan is exhausted
    (`exhausted`) or the call ceiling truncated the plan (`budget`). Injected primitives keep it token-free.
    """
    if keep_k < 1:
        raise ValueError(f"keep_k must be >= 1, got {keep_k}")
    levels = plan_levels(depth, branch, veri_ratio, max_calls)
    truncated = max_calls is not None and sum(levels) < branch * depth

    survivors: list[Candidate] = []
    calls = 0
    nodes = 0
    reason = "exhausted"

    for level_idx, n_props in enumerate(levels):
        parents: list[Optional[Candidate]] = [None] if level_idx == 0 else list(survivors)
        if not parents:                      # nothing survived to refine (shouldn't happen: keep_k>=1)
            break
        children: list[Candidate] = []
        for j in range(n_props):
            parent = parents[j % len(parents)]
            branch_id = f"L{level_idx}B{j}"
            _emit(on_event, stage="propose", level=level_idx, branch=branch_id,
                  parent=(parent.branch_id if parent else None))
            program = propose(brief) if parent is None else refine(parent, brief)
            calls += 1
            el, err = execute(program)
            crit = verify(el, brief) if el is not None else None
            cand = Candidate(branch_id=branch_id, program=program, ir=el, critique=crit, err=err,
                             score=score(crit), level=level_idx,
                             parent_id=(parent.branch_id if parent else None))
            nodes += 1
            children.append(cand)
            _emit(on_event, stage="evaluate", branch=branch_id, passed=cand.passed,
                  score=list(cand.score), build_error=err)

        # Prune: keep the top-keep_k of new children ∪ current survivors (monotonic — never lose the best).
        pool = children + survivors
        pool.sort(key=lambda c: c.score)
        survivors = pool[:keep_k]
        _emit(on_event, stage="select", level=level_idx,
              kept=[c.branch_id for c in survivors],
              pruned=[c.branch_id for c in pool[keep_k:]],
              best=survivors[0].branch_id)

        if survivors[0].passed:              # the deterministic critic is satisfied — done
            reason = "converged"
            break

    best = survivors[0] if survivors else None
    if best is not None and best.passed:
        reason = "converged"
    elif truncated:
        reason = "budget"
    _emit(on_event, stage="terminal", reason=reason,
          best=(best.branch_id if best else None), calls=calls)
    return SearchResult(best=best, calls_used=calls, reason=reason, levels=levels, nodes=nodes)
