# Driving Ludwig from any agent harness (MCP)

Ludwig speaks the **Model Context Protocol**: `cli.py mcp` is an MCP server (stdio) that exposes the
compiler's `compile / verify / plan / build / export` over the same contract the Studio uses
([docs/CONTRACT.md](CONTRACT.md)). Point Claude Code, opencode, Claude Desktop, or any MCP client at it
and the external agent designs; **Ludwig validates and executes**. This is the A-series thesis made
literal — *"fully agentic AI-first"* without Ludwig building a single line of agent chassis.

> The trust story is the pitch: the agent emits **ops as data**, never code. Ludwig strict-validates them
> and refuses anything malformed; a fabrication file never leaves on a failing critic. That is what
> "agent writes Blender Python" integrations structurally cannot claim.

## Wire it up

Needs the engine (`cadquery`, `ifcopenshell`), a `claude`-like CLI on `PATH` for `ludwig_compile`, and the
MCP SDK (`pip install mcp`). Run through the project venv.

```bash
# Claude Code
claude mcp add ludwig -- python3 /path/to/Ludwig/cli.py mcp

# any MCP client: spawn `python3 cli.py mcp` (stdio transport), cwd = the repo
```

Verify by hand:

```bash
python3 cli.py mcp          # starts the stdio server (Ctrl-C to stop)
```

## The tool surface (v1)

| Tool | Inference | What it does |
|---|---|---|
| `ludwig_compile(brief)` | Ludwig-side | NL brief → generate + verify + (on pass) write STEP/IFC/DXF. Returns the program, critic verdict, bbox, `artifacts_abs`. |
| `ludwig_verify(program)` | none | Execute + run the deterministic critic. Token-free, writes no files. Returns `{passed, critic[], bbox, dims, program}`. |
| `ludwig_plan(instruction, program)` | Ludwig-side | Propose validated ops (data) + summaries. Writes nothing. |
| `ludwig_build(program, ops, confirm=false)` | none | Apply agent-supplied ops (the security boundary). Malformed → rejected, nothing executed. Returns the new program, `diff`, and the `inverse` plan (undo). |
| `ludwig_export(program, confirm=false)` | none | Write fab files — behind the critic gate AND the permission gate. Returns `artifacts_abs`. |

Every result carries the critic verdict and `schema_version`. **MCP calls are token-free on Ludwig's
side** for verify/plan-application/export — the *caller's* model does the reasoning; when a harness drives
Ludwig by emitting ops, Ludwig runs zero inference.

## A reproducible walkthrough

1. **Compile.** `ludwig_compile("steel bracket 80×40×6 mm, two M8 clearance holes")` → `passed: true`
   over the critic's checks, and `artifacts_abs.step` — a STEP file on disk. (A brief that can't be made
   fabricable returns its failing report and **no** fab file.)
2. **Or the agent plans + builds** (token-free on Ludwig's side): `ludwig_build(program, [{"op":"SetParam",
   "name":"length","old":80,"new":120}])` → the edited solid + an `inverse` op that undoes it. A structural
   op (`{"op":"AddFeature","func":"clearance_hole","args":["M8",[0,0]]}`) returns `needs_confirmation` until
   re-called with `confirm=true` (see Permissions).
3. **Reject the bad.** `ludwig_build(program, [{"op":"RunShell","cmd":"rm -rf /"}])` → `{"rejected": true}`
   — the op is not a known kind, so it is refused and **nothing is executed**.
4. **Export.** `ludwig_export(program, confirm=true)` → `artifacts_abs` with the verified STEP/IFC/DXF paths;
   on a failing critic it refuses with the report and no files.

## Permissions

`ludwig_build`/`ludwig_export` obey `standards.yaml: permissions` — the same gate the Studio's mode-dial
sets ([docs/CONTRACT.md §4.1](CONTRACT.md)). For a headless agent, **"confirm" is an explicit re-call**,
not a dialog: a `confirm`-class action returns `needs_confirmation` (with the critic verdict inline for
export) until the call carries `confirm=true`. Modes: `auto` (per op class) · `plan` (nothing applies
without confirm) · `locked` (read-only). Defaults: `param_edit` applies live; `structural` and `export`
ask first.

## Non-negotiables (why this is safe to hand an agent)

- **The Op-API is the only write surface** (`agent/ops.parse_plan`): unknown op kind, unexpected field,
  missing field, or wrong value type → `ValueError`, nothing runs. Fuzzing this is the standing CI job.
- **The pre-export critic gate is inside the tool**, not around it — no fab file on a failing critic.
- **One daemon, one payload shape, many clients.** The MCP tools back onto the same `webapp.service` the
  Studio and CLI use; there is no forked "for agents" API.

See [CONTRACT.md](CONTRACT.md) for the exact payload/op/SSE shapes and the versioning policy.
