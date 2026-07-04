#!/usr/bin/env python3
"""A runnable proof of the Ludwig MCP trust story — the A4 demo, as a script you can actually run.

    .venv/bin/python examples/mcp_walkthrough.py            # token-free (no inference needed)
    .venv/bin/python examples/mcp_walkthrough.py --compile  # also drive ludwig_compile (needs a `claude` CLI)

It spawns the real stdio MCP server (`cli.py mcp`) as an external client would, and walks the whole
arc an agent harness sees — so the docs/MCP.md walkthrough is a thing you *watch happen*, not prose:

  1. verify   — the deterministic critic passes a good bracket (token-free)
  2. build    — an agent's param-edit op applies and returns its own inverse (undo) (token-free)
  3. REJECT   — an agent's shell-exec op is refused; NOTHING runs (the security boundary)
  4. critic   — a bracket with a 0.5 mm wall FAILS the critic (a real fab defect)
  5. gate     — export of that bad part is REFUSED; no fabrication file leaves
  6. export   — the good part asks-first (permission gate), then writes a verified STEP on confirm

The core (2–6) needs no inference at all — the caller's model does the reasoning; Ludwig runs zero
tokens. That is the pitch: the agent proposes *data*, Ludwig validates and executes. Exit code is
non-zero if any invariant breaks, so this doubles as a smoke test.
"""
from __future__ import annotations

import asyncio
import json
import sys

# A known-good bracket — the exact program a compile emits (so the core demo needs no inference).
GOOD = (
    'from toolkit import box, clearance_hole\n'
    'element = box("bracket", 80, 40, 6)\n'
    'element.register_dim("length", 80)\n'
    'element.register_dim("width", 40)\n'
    'element.register_dim("height", 6)\n'
    'clearance_hole(element, "M8", (30, 0))\n'
    'clearance_hole(element, "M8", (-30, 0))\n'
)

# The SAME bracket with one hole pushed to x=35 — a ⌀9 bore 0.5 mm from the edge. It builds a valid
# solid, but the wall is un-fabricable. A text-to-CAD tool emits this happily; Ludwig's critic won't.
BAD = GOOD.replace('clearance_hole(element, "M8", (30, 0))',
                   'clearance_hole(element, "M8", (35, 0))')

CHECK, CROSS, ARROW = "✓", "✗", "→"


def _payload(res) -> dict:
    """An MCP tool result → the dict Ludwig returned (structured content, or the JSON text block)."""
    return res.structuredContent or json.loads(res.content[0].text)


def _critic_line(d: dict) -> str:
    fails = [c for c in (d.get("critic") or []) if str(c.get("status")).lower() == "fail"]
    if not fails:
        n = sum(1 for c in (d.get("critic") or []) if str(c.get("status")).lower() == "pass")
        return f"{CHECK} critic passed ({n} checks)"
    return f"{CROSS} critic FAILED: " + "; ".join(f"{c['check']}: {c['message']}" for c in fails)


def _hd(step: str, title: str) -> None:
    print(f"\n{'─' * 72}\n{step}  {title}\n{'─' * 72}")


class DemoError(RuntimeError):
    """An invariant the trust story guarantees did not hold — the demo is the assertion."""


async def _run(do_compile: bool) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=["cli.py", "mcp"], cwd=".")
    good = GOOD

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await asyncio.wait_for(s.initialize(), 30)
            tools = {t.name for t in (await s.list_tools()).tools}
            print(f"Connected to the Ludwig MCP server. Tools: {', '.join(sorted(tools))}")

            if do_compile:
                _hd("0.", "compile — a natural-language brief becomes a verified model (uses inference)")
                res = await asyncio.wait_for(
                    s.call_tool("ludwig_compile",
                                {"brief": "a steel bracket, 80 x 40 x 6 mm, two M8 clearance holes"}), 420)
                d = _payload(res)
                print(f"   {_critic_line(d)}")
                step = (d.get("artifacts_abs") or {}).get("step")
                if not d.get("passed") or not step:
                    raise DemoError("compile did not return a passing critic + STEP path")
                print(f"   {CHECK} STEP written {ARROW} {step}")
                good = d.get("program") or good     # drive the rest of the demo off the compiled program

            _hd("1.", "verify — the deterministic critic passes a good part (token-free)")
            d = _payload(await s.call_tool("ludwig_verify", {"program": good}))
            print(f"   {_critic_line(d)}   bbox={d.get('bbox')}")
            if not d.get("passed"):
                raise DemoError("the known-good bracket did not pass verify")

            _hd("2.", "build — an agent's param-edit op applies and returns its own undo (token-free)")
            op = {"op": "SetParam", "name": "length", "old": 80, "new": 120}
            print(f"   agent proposes (as DATA, not code): {json.dumps(op)}")
            d = _payload(await s.call_tool("ludwig_build", {"program": good, "ops": [op]}))
            if not d.get("built"):
                raise DemoError(f"a valid param-edit op was not applied: {d}")
            print(f"   {CHECK} applied {ARROW} {_critic_line(d)}")
            if d.get("inverse"):
                print(f"   {CHECK} inverse (undo) returned: {json.dumps(d['inverse'])}")

            _hd("3.", "REJECT — an agent's shell-exec op is refused; nothing runs (the boundary)")
            evil = {"op": "RunShell", "cmd": "rm -rf /"}
            print(f"   agent proposes: {json.dumps(evil)}")
            d = _payload(await s.call_tool("ludwig_build", {"program": good, "ops": [evil]}))
            if not d.get("rejected") or d.get("built"):
                raise DemoError(f"a malformed/unknown op was NOT rejected: {d}")
            print(f"   {CHECK} rejected, nothing executed {ARROW} {d.get('error')}")

            _hd("4.", "critic — a bracket with a 0.5 mm wall FAILS (a real fabrication defect)")
            d = _payload(await s.call_tool("ludwig_verify", {"program": BAD}))
            print(f"   {_critic_line(d)}")
            if d.get("passed"):
                raise DemoError("the un-fabricable (0.5 mm wall) part wrongly passed the critic")

            _hd("5.", "gate — exporting that bad part is REFUSED; no fab file leaves")
            d = _payload(await s.call_tool("ludwig_export", {"program": BAD, "confirm": True}))
            if d.get("exported") or (d.get("artifacts_abs") or {}):
                raise DemoError("a failing-critic part was exported — the fab gate leaked")
            print(f"   {CHECK} export refused on the failing critic; artifacts_abs = {{}}")

            _hd("6.", "export — the good part asks first (permission gate), then writes a verified STEP")
            d = _payload(await s.call_tool("ludwig_export", {"program": good}))   # confirm defaults False
            if d.get("exported"):
                raise DemoError("export applied without confirmation — the permission gate leaked")
            print(f"   {CHECK} needs_confirmation (permission gate) — re-calling with confirm=true …")
            d = _payload(await s.call_tool("ludwig_export", {"program": good, "confirm": True}))
            step = (d.get("artifacts_abs") or {}).get("step")
            if not d.get("exported") or not step:
                raise DemoError(f"confirmed export did not write a STEP: {d}")
            print(f"   {CHECK} verified STEP written {ARROW} {step}")

    print(f"\n{'═' * 72}\n{CHECK} All trust invariants held. The agent proposed; Ludwig validated and "
          f"executed.\n{'═' * 72}")


def main() -> int:
    do_compile = "--compile" in sys.argv[1:]
    try:
        import mcp  # noqa: F401
    except ImportError:
        print("this walkthrough needs the MCP SDK (`pip install mcp`) and the engine (cadquery).")
        return 1
    try:
        asyncio.run(_run(do_compile))
    except DemoError as e:
        print(f"\n{CROSS} INVARIANT VIOLATED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
