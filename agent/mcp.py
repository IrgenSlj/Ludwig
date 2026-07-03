"""Ludwig MCP server (S-MCP, session A2) — the second face of the daemon's contract.

Exposes Ludwig's `compile / verify / export` over the Model Context Protocol so any harness — Claude
Code, opencode, Claude Desktop, OpenClaw, Copilot… — becomes a Ludwig frontend. "Fully agentic
AI-first" becomes literally true: the external agent drives; Ludwig validates and executes. Wire it in:

    claude mcp add ludwig -- python3 cli.py mcp        # (or `ludwig mcp` once packaged)

Design (HARNESS_BRIEF §3.2):
- **The MCP SDK is imported LAZILY**, inside `build_server()` only — `import agent.mcp` and the
  pure-Python spine / `--selftest` stay green on a machine without the SDK (CLAUDE.md convention).
- **Every result carries the critic verdict + `schema_version`** (the A1 contract, now consumed
  externally — docs/CONTRACT.md). The same `webapp.service` functions the Studio uses back these tools:
  one daemon, one payload shape, many clients (principle 9). No "for agents" API is forked.
- **Export refuses on a failing critic** — the pre-export gate lives INSIDE the tool, not around it, so
  no fabrication file ever leaves on an unverified model.
- **Data in, never code out.** `compile` uses Ludwig's own BYO inference to generate the parametric
  program; `verify`/`export` are token-free (the caller spends zero Ludwig inference). The Op-API
  (`ops.parse_plan`, exposed by A3) stays the only *write-by-the-agent* surface — malformed ops are
  rejected, never exec'd (principle 10). The v1 tool surface is deliberately small; plan/build/edit and
  server-side permissions land in A3.
"""
from __future__ import annotations

from pathlib import Path


def _abs_artifacts(result: dict, out: Path) -> dict:
    """Resolve the result's artifact filenames to absolute paths so the *calling* agent (whose CWD is
    its own, not Ludwig's) can open the files it just had written."""
    arts = result.get("artifacts") or {}
    return {k: str((Path(out) / v).resolve()) for k, v in arts.items() if isinstance(v, str)}


def build_server(name: str = "ludwig"):
    """Construct (don't run) the FastMCP server with Ludwig's v1 tools. The SDK import lives here so the
    module imports without it; call this only when you actually intend to serve."""
    from mcp.server.fastmcp import FastMCP

    from webapp import service

    server = FastMCP(name)
    out = service.OUT

    @server.tool()
    def ludwig_compile(brief: str) -> dict:
        """Compile a natural-language brief into a verified, fabricable model.

        Ludwig generates the parametric program, executes the exact OCCT B-rep, runs the deterministic
        critic, and — only if every check passes — writes the derived fabrication files (STEP for CAM,
        IFC for BIM, DXF drawings). Returns the re-promptable `program`, the `critic` verdict, `passed`,
        the `bbox`, and absolute artifact paths under `artifacts_abs`. A brief that can't be made
        fabricable returns its failing critic report and NO fab file.
        """
        r = service.compile_to_result(brief)
        r["artifacts_abs"] = _abs_artifacts(r, out)
        return r

    @server.tool()
    def ludwig_verify(program: str) -> dict:
        """Execute a Ludwig program and run the deterministic critic — token-free, writing NO files.

        Returns `{passed, critic[], bbox, dims, program, schema_version}`. The critic is manifold /
        watertight / dimensional / semantic checks — not eyeballing. Use this to check a model (yours or
        a prior compile's) before spending an export.
        """
        return service.verify_to_result(program)

    @server.tool()
    def ludwig_export(program: str) -> dict:
        """Execute + verify a program and, if the critic passes, write the derived fabrication files.

        The pre-export critic gate is INSIDE this tool: on a failing critic it refuses and returns the
        report with no `artifacts_abs`, exactly as `cli.py` does — no fab file ever leaves on an
        unverified model. On success returns absolute paths to the STEP / IFC / DXF / recipe.
        """
        r = service.adopt_to_result(program)
        r["artifacts_abs"] = _abs_artifacts(r, out) if r.get("passed") else {}
        return r

    return server


def main() -> int:
    """`cli.py mcp` — run the MCP server over stdio (the `claude mcp add ludwig -- python3 cli.py mcp`
    path). One process; HTTP transport reuses the daemon later (A-series long-term)."""
    build_server().run()   # FastMCP defaults to the stdio transport
    return 0
