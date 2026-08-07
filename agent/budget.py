"""Spend projection + the confirmation gate for token-spending runs (`budget.cost_confirm_usd`).

`ludwig.toml` has always documented `budget.cost_confirm_usd` as "bench/large runs print a projected
cost and require confirmation above this" — this module is what makes that true. It exists because
the one command the B-series is built to run, `cli.py --eval --bench edit --live`, defaults to the
FULL 748-row set at the best (most expensive) tier: forget `--bench-limit` and you buy hours of
opus calls you didn't mean to.

Two things are worth being precise about, because this is a number we show a human before they
spend money (principle: measure, don't assert):

- **Call count is exact.** rows x (1 + repair rounds) is arithmetic over the sampled rows, not a guess.
- **Dollars are an ESTIMATE, and labelled one everywhere it surfaces.** The inference seam shells out
  to a provider CLI (`agent/inference.py`) which reports no token usage, so there is no ground truth
  to read back. We size the prompt from the actual row text we are about to send — not a per-call
  constant — and convert characters to tokens with one stated ratio. Rates live in
  `standards.yaml: pricing` so they are updatable without a code change and are never magic numbers.

The estimate is deliberately built to over-state rather than under-state: the caller is deciding
whether to spend, and a projection that reads low is worse than one that reads high.
"""
from __future__ import annotations

import os
import sys
from typing import Iterable, Optional

# Characters per token for source code + terse English instructions. Code tokenizes denser than
# prose (punctuation, short identifiers); 3.5 is the conservative (token-heavy) end of the usual
# 3.5-4.5 band, chosen so the projection errs high. Only ever used for the DOLLAR estimate — the
# call count below never touches it.
_CHARS_PER_TOKEN = 3.5

# Fallback rates (USD per million tokens) if `standards.yaml: pricing` is missing or unreadable.
# Keyed by the tier LABEL the loop resolves (standards.yaml: inference.tiers), not a model id, so a
# retier doesn't silently price the run against the wrong model.
_DEFAULT_RATES = {
    "best":  {"input": 5.0,  "output": 25.0},   # opus-class
    "cheap": {"input": 1.0,  "output": 5.0},    # haiku-class
}


class SpendRefused(RuntimeError):
    """The human declined a run whose projected cost crossed the confirmation threshold."""


def rates_for(tier: str) -> dict:
    """USD-per-million-tokens for a tier label, from `standards.yaml: pricing` over the defaults.

    Never raises — an unreadable or absent standards file falls back to the built-in rates, because a
    missing price list must not be the reason a run can't be projected."""
    table = dict(_DEFAULT_RATES)
    try:
        from toolkit.standards import load
        block = (load() or {}).get("pricing") or {}
        for tier_name, vals in block.items():
            if isinstance(vals, dict) and tier_name in table:
                table[tier_name] = {
                    "input": float(vals.get("input", table[tier_name]["input"])),
                    "output": float(vals.get("output", table[tier_name]["output"])),
                }
    except Exception:
        pass
    return table.get(tier, _DEFAULT_RATES["best"])


def project_edit_bench(rows: Iterable[dict], *, rounds: int, tier: str = "best",
                       prompt_overhead_chars: int = 700) -> dict:
    """Project the cost of `cli.py --eval --bench edit --live` over `rows`.

    Sizes each call from the row we will actually send (`orig_code` + `instruction`) plus the fixed
    prompt scaffolding, and assumes the reply is a full program (~the size of the original). Repair
    rounds re-send the same prompt with an error appended, so they cost about the same again.

    `calls` is the WORST case — every row using all its repair rounds. That is the right number to
    show before spending, since it is the ceiling the caller is authorising, and it is stated as a
    ceiling wherever it surfaces.
    """
    rows = list(rows)
    r = rates_for(tier)
    calls_per_row = 1 + max(0, rounds)
    in_chars = out_chars = 0
    for row in rows:
        code = str(row.get("orig_code") or "")
        instr = str(row.get("instruction") or "")
        in_chars += (len(code) + len(instr) + prompt_overhead_chars) * calls_per_row
        out_chars += len(code) * calls_per_row          # the reply is the full updated program
    in_tok = in_chars / _CHARS_PER_TOKEN
    out_tok = out_chars / _CHARS_PER_TOKEN
    usd = (in_tok / 1e6) * r["input"] + (out_tok / 1e6) * r["output"]
    return {
        "rows": len(rows),
        "calls": len(rows) * calls_per_row,
        "input_tokens": round(in_tok),
        "output_tokens": round(out_tok),
        "usd": usd,
        "tier": tier,
        "rates": r,
    }


def format_projection(p: dict, *, pace_s: float = 0.0) -> str:
    """The block a human reads before authorising a spend. Says ESTIMATE out loud."""
    lines = [
        f"  rows              {p['rows']}",
        f"  model calls       {p['calls']} (ceiling — every row using all repair rounds)",
        f"  tier              {p['tier']}  (${p['rates']['input']:g}/${p['rates']['output']:g} per Mtok in/out)",
        f"  tokens (est.)     {p['input_tokens']:,} in · {p['output_tokens']:,} out",
        f"  COST (ESTIMATE)   ${p['usd']:.2f}",
    ]
    if pace_s:
        mins = (p["calls"] * pace_s) / 60.0
        lines.append(f"  wall time         >= {mins:.0f} min (at {pace_s:g}s pacing between rows)")
    lines.append("  NB the estimate is sized from the prompts we will send; the provider CLI reports")
    lines.append("     no token usage, so the dollar figure cannot be exact. It errs high on purpose.")
    return "\n".join(lines)


def confirm_spend(projection: dict, *, threshold: float, label: str = "this run",
                  pace_s: float = 0.0, assume_yes: bool = False,
                  stream=None) -> None:
    """Print the projection and, above `threshold`, require an explicit go-ahead. Raises `SpendRefused`.

    Non-interactive callers (CI, a piped shell) have no tty to answer on, so an unattended run above
    the threshold REFUSES rather than silently proceeding — pass `--yes` (or `LUDWIG_ASSUME_YES=1`)
    to authorise it up front. `threshold <= 0` disables the gate entirely.
    """
    out = stream or sys.stdout
    print(f"\nprojected spend for {label}:", file=out)
    print(format_projection(projection, pace_s=pace_s), file=out)
    if threshold <= 0 or projection["usd"] <= threshold:
        print(f"  -> under the ${threshold:.2f} confirmation threshold; proceeding.\n", file=out)
        return
    if assume_yes or os.environ.get("LUDWIG_ASSUME_YES", "").strip().lower() in ("1", "true", "yes", "on"):
        print(f"  -> over the ${threshold:.2f} threshold; authorised up front (--yes).\n", file=out)
        return
    if not sys.stdin.isatty():
        raise SpendRefused(
            f"projected ${projection['usd']:.2f} exceeds budget.cost_confirm_usd (${threshold:.2f}) and "
            "there is no terminal to confirm on. Re-run with --yes (or LUDWIG_ASSUME_YES=1) to "
            "authorise, --bench-limit N to shrink the run, or raise budget.cost_confirm_usd.")
    print(f"  -> over the ${threshold:.2f} confirmation threshold.", file=out)
    try:
        answer = input("     type 'yes' to spend it: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer != "yes":
        raise SpendRefused("spend declined — nothing was sent to the model.")
    print("", file=out)


def threshold_from_config(cfg=None) -> float:
    """`budget.cost_confirm_usd`, resolved from ludwig.toml. Never raises — a broken config must not
    be the reason a spend gate is skipped, so an unreadable one falls back to the dataclass default."""
    try:
        if cfg is None:
            from agent.config import load_config
            cfg = load_config()
        return float(cfg.budget.cost_confirm_usd)
    except Exception:
        from agent.config import BudgetConfig
        return float(BudgetConfig().cost_confirm_usd)


def oracle_gate(rows: list, *, on_progress=None) -> Optional[str]:
    """Validate the grader against its own oracle on THESE rows before any token is spent.

    `run_bench_edit`'s docstring and STATUS.md both call this a gate, but until now it was a
    convention: `--live` skipped oracle mode entirely and trusted the operator to have run it
    earlier, on some other sample. It is cheap (token-free, kernel-only) and it is the difference
    between a bad number and a caught bug, so `--live` now runs it on the exact rows it is about to
    grade. Returns None when the grader passes, else the reason it did not.
    """
    from eval import editbench

    gt_sum, gt_res = editbench.run(rows, editbench.predict_oracle, on_row=on_progress)
    bad = [r for r in gt_res if not r.get("ungradeable") and r["score"] < 0.999]
    if bad:
        names = ", ".join(r["record_id"] for r in bad[:3])
        return (f"the grader scores {len(bad)}/{gt_sum['n']} ground-truth row(s) below 1.000 "
                f"({names}{' …' if len(bad) > 3 else ''}) — it does not pass its own oracle on this "
                "sample, so a live number graded against it would not be trustworthy.")
    return None
