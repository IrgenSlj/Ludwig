# Ludwig — the wire contract (`schema_version 1.0`)

*The versioned JSON contract every client speaks: the Studio (three.js), the CLI, the macOS shell, and
— from A2 — any external agent harness over MCP. One daemon, one payload shape, many clients
(HARNESS_BRIEF §2, principle 9). This document is the reference; the code in `webapp/service.py`,
`agent/ops.py`, and `agent/runtime.py` is the source of truth. If they disagree, the code wins and this
doc is the bug.*

The daemon is `webapp/server.py` + `webapp/service.py` (`cli.py --serve`). The MCP server (A2) wraps the
same `service.py` functions, so the payloads below are identical whether they arrive over HTTP, SSE, or an
MCP tool result.

---

## 1. Versioning

Every result payload carries a top-level `schema_version` string (currently `"1.0"`). It is stamped by
`service.stamp()` / the `@_versioned` decorator on each public result builder, so the version travels with
the **data**, not the transport.

- **`schema_version` = `MAJOR.MINOR`.** A **MINOR** bump is additive and backward-compatible (a new
  optional field). A **MAJOR** bump is a breaking change to an existing field's name, type, or meaning, or
  to the Op schema / SSE event shapes.
- **Dual-support rule:** a breaking (MAJOR) change ships with **one release of dual support** — the old
  shape and the new shape are both served — before the old shape is removed. Clients pin the MAJOR they
  understand and degrade gracefully on an unknown MINOR (ignore unknown fields).
- Adding a key to the payload does **not** require a bump only if every existing client tolerates unknown
  keys (they do). Renaming or removing a key **does**.

---

## 2. The result payload

Returned by `compile / edit / adopt / build / hole-move` (the `_assemble` shape). The canonical, fullest
form:

```jsonc
{
  "schema_version": "1.0",
  "program":  "element = box(\"bracket\", 80, 40, 6)\n...",  // the re-promptable recipe source (the truth)
  "id":       "bracket",           // element id (null on a build failure)
  "type":     "box",               // element type   (null on a build failure)
  "rounds":   0,                   // repair rounds the loop took
  "passed":   true,                // critic all-pass — the fab gate (STEP/IFC only when true)
  "error":    null,                // build error string, or null

  "bbox":     {"length": 80.0, "width": 40.0, "height": 6.0},   // mm, 4dp; null if no geometry
  "dims":     [                    // named dimensions, deduped by name
    {"name": "length", "value": 80, "unit": "mm", "axis": 0, "editable": true}
    // axis: 0/1/2 for an extent bound to a bbox axis, else null. editable: a slider/face-drag is offered.
  ],
  "critic":   [                    // deterministic critic report — see §3
    {"check": "manifold", "status": "pass", "message": "...", "element_id": null, "severity": "error"}
  ],
  "estimate": {"volume_cm3": 19.2, "mass_kg": 0.151, "material": "Steel",
               "grade": "S235", "cost": 0.14, "currency": "EUR"},   // verified fabricability; null if unknown

  "mesh":     {"positions": [x,y,z, ...], "indices": [i,j,k, ...],  // three.js viewer mesh (best-effort)
               "center": [cx,cy,cz], "radius": 42.1},               // null if tessellation failed
  "mesh_error": "RuntimeError: ...",   // present ONLY when mesh is null due to a tessellation failure
  "sketch2d": null,                    // the solved 2D profile loop when the element is a sketch, else null
  "holes":    [{"at": [-25, 0], "dia": 9.0, "kind": "M8"}],   // hole features (a picked hole → its literal)
  "children": [                        // an assembly's parts, each tessellated on its own for selection
    {"id": "top", "type": "box", "dims": [...], "mesh": {...}}
  ],

  "artifacts": {                       // files written under out/<session>/ — only on passed:true (fab gate)
    "recipe": "bracket.py",            // always written (the program text)
    "step":   "bracket.step",          // STEP    (fab)   — passed only
    "ifc":    "bracket.ifc",           // IFC     (BIM)   — passed only
    "svg":    "bracket.svg",           // HLR drawing     — passed only, best-effort
    "dxf":    "bracket.dxf",           // shop drawing    — passed only, best-effort
    "section-dxf": "bracket_section.dxf",
    "drawing_preview": "bracket.png",  // PNG preview beside the DXF, if present
    "svg_error": "..."                 // "<label>_error" appears if that one backend threw (others still ran)
  }
}
```

A **build failure** collapses to the header only: `program`, `id:null`, `type:null`, `passed:false`,
`error:"…"`, empty `dims`/`critic`/`children`, `bbox:null`, `mesh:null`, `artifacts:{}` — plus
`schema_version`.

**Per-path additions** (the same base shape, extra keys):

| Path | Adds |
|---|---|
| `edit`, `build`, `hole-move`, sketch/span/fast edits | `"diff": {"added": int, "removed": int, "text": "<unified diff>"}` |
| deterministic (no-LLM) edits | `"fast": true` |
| `edit` (LLM path) | `"fast": false`, `"instruction": "<text>"` |
| `build` / `build_from_ops` | `"built": true`, `"inverse": [<op>, ...]` (the undo plan, serialized ops) |
| `adopt` | `"adopted": true` |

**Other result shapes** (not `_assemble`):

- **explore** → `{"schema_version", "prompt": "<text>", "variants": [<variant>, ...]}` where each variant is
  a file-free snapshot (`program`, `passed`, `id`, `type`, `bbox`, `dims`, `critic`, `mesh`, `estimate`,
  `error`, `rank`). Only the *adopted* variant pays the backend/fab cost.
- **plan** → `{"schema_version", "ok": true, "instruction", "ops": [<op>, ...], "summary": ["<one-liner>", ...]}`.
  Proposes; writes nothing.
- **section** → `{"schema_version", "ok": true, "id", "type", "axis": "x|y|z", "offset": float,
  "mesh": {...}, "span": float, "bbox": {...}}`, or `{"schema_version", "ok": false, "reason": "...", "axis",
  "offset"}` when the plane misses the solid.
- **agent_stream** (final) → the variant snapshot plus `{"program", "applied": [<op>, ...], "ok": bool}`.
- **error** (any endpoint that raised) → `{"schema_version", "fatal": "<ExcType>: <message>"}`. The daemon
  never returns a silent 500; the reason is in `fatal`.

---

## 3. The critic report

Each check in `critic[]`:

| field | meaning |
|---|---|
| `check` | the check's name (`manifold`, `watertight`, `dimensional`, a sketch-DoF check, a pack check…) |
| `status` | `"pass"` \| `"fail"` \| `"warn"` (the `CheckStatus` value) |
| `message` | human-readable detail; for a pack check this carries the domain language (A8–A9) |
| `element_id` | which element the check is about, or null (so the UI paints Ambient Correctness on it) |
| `severity` | `"error"` \| `"warning"` \| `"critical"` — amber (warning/below-spec) vs red (error/critical) |

`passed` at the payload top level is `true` iff every check passes. **The fab gate keys off `passed`:** no
STEP/IFC is written on a failing critic. An MCP `export` refuses identically — the pre-export hook is
inside the tool, not around it (HARNESS_BRIEF §3.2).

---

## 4. The Op schema (`agent/ops.py`)

An **Op is data, not code.** A planner (the model, or an external agent over MCP) emits Ops as JSON; the
daemon strict-validates them with `parse_plan` and renders them to toolkit source. The model never hands us
Python to `exec()` — this is the security boundary (HARNESS_BRIEF principle 10; ClawHub is the standing
proof of principle 6). An unknown op kind, an unexpected field, a missing required field, or a wrong value
type **raises**, and nothing is executed.

A plan is a JSON list of op dicts (or `{"ops": [...]}`). Each dict has an `"op"` kind and exactly that
kind's declared fields:

| `op` | required fields | renders to |
|---|---|---|
| `AddElement` | `kind` (str), `id` (str), `args` (list) | `element = <kind>("<id>", *args)` |
| `AddFeature` | `func` (str); optional `args` (list), `target` (str, default `"element"`) | `<func>(<target>, *args)` |
| `Place` | `target` (str), `offset` (list) | `place(<target>, (dx,dy,dz))` |
| `Assemble` | `id` (str), `parts` (list); optional `kind` (str, default `"assembly"`) | `element = <kind>("<id>", *parts)` |
| `SetParam` | `name` (str), `old` (number), `new` (number) | edits an existing program's literal; `apply()` returns the new text **and its inverse `SetParam`** (undoable) |

Example plan (the bracket):

```json
[
  {"op": "AddElement", "kind": "box", "id": "bracket", "args": [80, 40, 6]},
  {"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [-25, 0]]},
  {"op": "AddFeature", "func": "clearance_hole", "args": ["M8", [25, 0]]}
]
```

Validation guarantees (enforced by `parse_plan`):
- unknown `op` kind → `ValueError` (nothing rendered);
- an extra/unexpected field → `ValueError`;
- a missing required field → `ValueError`;
- a field of the wrong JSON type (e.g. a `SetParam.new` that is a list, or an `AddElement.id` that is a
  number) → `ValueError`.

`SetParam.apply()` additionally refuses a **non-invertible** edit: if `new` already occurs as a distinct
literal in the program, the inverse would corrupt those occurrences on undo — it raises rather than produce
a lossy undo. Serialized ops (the `inverse[]` / `ops[]` wire form) are `{"op": "<Kind>", ...fields}`.

---

## 5. SSE event stream

Two streaming endpoints emit `text/event-stream`; each line is `data: <json>\n\n`. Both end with a single
terminal `result` or `error` event whose payload is a §2 result.

### `GET /api/compile_stream?prompt=…` — the compile/repair loop

Loop-stage events are wrapped as `{"event": "stage", ...}`:

| `stage` | `status` | extra fields |
|---|---|---|
| `codegen` | `running` / `done` | `candidate`, `candidates` |
| `execute` | `running` / `done` / `failed` | `candidate`, `candidates` |
| `critic` | `running` / `done` | `candidate`, `candidates`, failure summary |
| `select` | `done` | `candidates`, chosen candidate |
| `repair` | `running` / `done` | `round` |
| `derive` | `running` / `done` / `failed` | `backend` (`svg`/`dxf`/`section-dxf`/…), `message` on failure |

### `GET /api/agent_stream?instruction=…&seed=…` — the op-planner runtime

Op events are emitted directly (not wrapped in `stage`):

| `event` | fields |
|---|---|
| `op` | `op` (serialized op), `summary` (one-liner) |
| `skipped` | `op`, reason |
| `applied` | `op` |
| `done` | `state` = `{"program", "dims"}` |
| `cancelled` | — (Stop was honoured; zero ops) |
| `error` | `message` |

### Terminal events (both streams)

- `{"event": "result", "result": { …§2 payload with schema_version… }}`
- `{"event": "error", "fatal": "<ExcType>: <message>"}`

---

## 6. HTTP endpoints (current transport)

Read-only / streaming (GET): `/api/gallery`, `/api/compile_stream`, `/api/agent_stream`, `/out/<file>`,
`/vendor/<file>`.

Write / compute (POST, JSON body ≤ 256 KB): `/api/compile`, `/api/edit`, `/api/explore`, `/api/adopt`,
`/api/preview`, `/api/section`, `/api/hole`, `/api/plan`, `/api/build`. Each returns a §2 result (or an
error payload).

**DEMO mode** (`LUDWIG_DEMO=1`, the public box) locks the write surface to the trusted gallery seeds with
numeric edits only: generation/planning (which need inference and exec model-authored code) are refused,
and every dimension that reaches the kernel is envelope-bounded. Local `cli.py --serve` keeps full
behaviour. See `webapp/safety.py`.

The MCP server (A2) and the D-series daemon (`/api/health`, `/api/shutdown`, `--token`, ephemeral `--port
0`) extend this same contract — they do not fork it.
