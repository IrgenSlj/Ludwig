"""Permission policy (session A3) — the shared gate over the agent-facing WRITE surface.

The Op-API is the only way an agent writes (data-ops, never exec'd — principle 10); this module decides
*whether* a validated plan may be APPLIED, and it is consulted from the one place both transports pass
through: `webapp.service.build_from_ops` (behind HTTP `/api/build`) and the MCP `ludwig_build` /
`ludwig_export` tools. One daemon, one policy (principle 9).

The subtlety A3 turns on: over stdio the caller is an autonomous agent, not a human clicking Accept — so
"confirm" cannot mean a dialog. Here it means: the tool REFUSES and returns `needs_confirmation` unless
the call carries an explicit `confirm=true`. In the Studio, the mode-dial's state + a human Accept supply
that `confirm` — the *same* policy, two transports. A missing/partial `permissions` block is permissive
(back-compat: today's behaviour).
"""
from __future__ import annotations

# The defaults a missing/partial standards block falls back to. `structural`/`export` default to `confirm`
# so a headless agent can't silently add geometry or write fab files without saying so; `param_edit`
# (a slider value as data) is `auto` so the common live-tweak stays instant.
_DEFAULT = {"mode": "auto", "param_edit": "auto", "structural": "confirm", "export": "confirm"}
_MODES = ("auto", "plan", "locked")

# A live mode override the Studio's mode-dial sets over HTTP. **Process-global**, not per-daemon:
# `webapp.service.build_from_ops` is the one shared write path and it consults `policy()` with no
# server in hand, so threading a per-server mode through would change the signature the MCP tools use
# too. That is the right trade for the deployment model — one daemon per process, and the MCP server
# is a separate process — but it is worth stating rather than implying, because the token beside it
# IS per-server (webapp/server.py sets it on the instance so two daemons can coexist with distinct
# tokens). Two daemons in ONE process therefore share a mode dial. `None` → use the standards value.
_RUNTIME_MODE: str | None = None


def set_mode(mode: str | None) -> str:
    """Set (or clear, with None) the live mode override; returns the effective mode. Rejects garbage."""
    global _RUNTIME_MODE
    _RUNTIME_MODE = mode if mode in _MODES else None
    return policy()["mode"]


def policy() -> dict:
    """The effective policy: standards.yaml's `permissions` block merged over the defaults (unknown keys
    ignored), with `mode` overridden by the live dial setting if one is active. Never raises — a
    broken/absent standards file yields the permissive default."""
    try:
        from toolkit.standards import load
        block = (load() or {}).get("permissions") or {}
    except Exception:
        block = {}
    merged = {**_DEFAULT, **{k: v for k, v in block.items() if k in _DEFAULT}}
    if merged["mode"] not in _MODES:
        merged["mode"] = "auto"
    if _RUNTIME_MODE in _MODES:
        merged["mode"] = _RUNTIME_MODE
    return merged


def classify(plan) -> str:
    """`param_edit` if the plan is only SetParam ops (a slider/param tweak expressed as data), else
    `structural` (it adds/assembles/places geometry). An empty plan is `param_edit` — nothing structural
    happens."""
    from agent.ops import SetParam
    ops = getattr(plan, "ops", plan) or ()
    return "param_edit" if all(isinstance(o, SetParam) for o in ops) else "structural"


def decide(action: str, plan, confirm: bool = False, *, pol: dict | None = None):
    """Decide whether `action` ('build' | 'export') may proceed. Returns (verdict, reason) where
    verdict is one of 'allow' | 'needs_confirmation' | 'denied'. Pure — pass `pol` to test without I/O."""
    pol = pol or policy()
    mode = pol.get("mode", "auto")
    if mode == "locked":
        return ("denied", "permissions: locked (read-only) — build/export are refused")
    if mode == "plan":
        rule, why = "confirm", "plan mode"                 # nothing applies without an explicit confirm
    elif action == "export":
        rule, why = pol.get("export", "confirm"), "export policy"
    else:                                                  # build: gate by the plan's op class
        cls = classify(plan)
        rule, why = pol.get(cls, "confirm"), f"{cls} policy"
    if rule == "auto" or confirm:
        return ("allow", "")
    return ("needs_confirmation", f"permissions: {action} needs confirmation ({why})")
