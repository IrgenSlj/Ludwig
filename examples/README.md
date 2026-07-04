# examples

Runnable demonstrations of Ludwig's surfaces. Run them through the project venv (`.venv/bin/python`).

- **`mcp_walkthrough.py`** — the MCP trust story as a script you watch execute. Spawns the real stdio
  MCP server and drives the whole arc (verify → build+inverse → reject a malicious op → critic catches a
  0.5 mm-wall defect → export refused → confirmed export writes a verified STEP), asserting each
  invariant. The core is token-free (no inference). See [docs/MCP.md](../docs/MCP.md).

  ```bash
  .venv/bin/python examples/mcp_walkthrough.py            # token-free
  .venv/bin/python examples/mcp_walkthrough.py --compile  # also drive ludwig_compile (needs a `claude` CLI)
  ```
