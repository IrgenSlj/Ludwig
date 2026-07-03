"""MCP server (S-MCP, A2) — the second face of the contract, exercised by a REAL stdio MCP client.

Token-free end to end: it drives `ludwig_verify` + `ludwig_export` over a spawned `cli.py mcp` process
(no inference). `ludwig_compile` uses Ludwig's own BYO inference, so it's covered by the service-level
compile test + the selftest tool registry rather than a token-spending round-trip here."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("cadquery")           # the tools execute real B-rep
pytest.importorskip("mcp")                # the SDK — skip cleanly where it isn't installed

from webapp import service

ROOT = Path(__file__).resolve().parent.parent
GOOD = ('element = box("bracket", 80, 40, 6)\n'
        'clearance_hole(element, "M8", (-25, 0))\n'
        'clearance_hole(element, "M8", (25, 0))\n')
BAD = "x = 1  # no `element` is defined → the program can't build\n"


def test_verify_to_result_is_token_free_and_file_free(tmp_path):
    r = service.verify_to_result(GOOD)
    assert r["passed"] is True and r["id"] == "bracket"
    assert r["schema_version"] == service.SCHEMA_VERSION
    assert not r.get("artifacts")                       # verify writes NO files
    bad = service.verify_to_result(BAD)
    assert bad["passed"] is not True                    # a non-building program → not passed, no crash


def _call_tool(tool: str, args: dict):
    """Spawn `cli.py mcp` and drive one tool call through a real MCP stdio client (bounded timeouts so a
    hung server can never wedge the suite)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["cli.py", "mcp"], cwd=str(ROOT))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), 30)
                return await asyncio.wait_for(session.call_tool(tool, args), 90)

    return asyncio.run(run())


def _data(res) -> dict:
    """The tool's dict payload — FastMCP serializes a plain `-> dict` return into a JSON text block
    (structuredContent stays None unless the return is a typed/pydantic model)."""
    if res.structuredContent is not None:
        return res.structuredContent
    return json.loads(res.content[0].text)


def test_mcp_stdio_lists_the_v1_tools():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["cli.py", "mcp"], cwd=str(ROOT))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), 30)
                return await asyncio.wait_for(session.list_tools(), 30)

    tools = {t.name for t in asyncio.run(run()).tools}
    assert {"ludwig_compile", "ludwig_verify", "ludwig_export"} <= tools


def test_mcp_stdio_verify_roundtrip():
    res = _call_tool("ludwig_verify", {"program": GOOD})
    assert res.isError is False
    data = _data(res)
    assert data["passed"] is True and data["schema_version"] == service.SCHEMA_VERSION


def test_mcp_stdio_export_gates_on_the_critic():
    # a verified model → the fab gate lets STEP through, as an absolute path the caller can open
    ok = _data(_call_tool("ludwig_export", {"program": GOOD}))
    assert ok["passed"] is True
    assert "step" in ok["artifacts_abs"] and Path(ok["artifacts_abs"]["step"]).exists()
    # a non-building model → refused: no artifacts leave
    bad = _data(_call_tool("ludwig_export", {"program": BAD}))
    assert bad["passed"] is not True and not bad["artifacts_abs"]
