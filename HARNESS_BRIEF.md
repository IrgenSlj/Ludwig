# LUDWIG — Agentic Harness Brief (the A-series)

*Companion to BRIEF.md — it AMENDS, never replaces. Read BRIEF.md first, then this, every session.
This document fixes the decisions for the post-R34 direction: Ludwig as the trusted geometry hand
of the agentic ecosystem. Sessions are A1… (Agentic); the macOS workstream is D1… (see
docs/MACOS_APP_PLAN.md); the UI workstream is in docs/DESIGN_BRIEF_STUDIO_V2.md.*

> **The one-line thesis extension:** BRIEF.md made Ludwig a compiler with a deterministic critic.
> This brief makes that compiler **addressable by every agent harness in the world** — without
> building a single line of generic agent chassis ourselves.

---

## 0. What changed, and why this document exists

R1–R34 shipped the interaction core: the deterministic DAG evaluator, direct manipulation, the
Op-API (the LLM emits validated JSON ops — data, never exec'd), the streaming runtime with
injectable inference, 2D sketches, true sections, typed AEC elements, and a 93% live first-pass
rate. The product question that follows is the one this brief answers: *how does "fully agentic
AI-first" get built without regressing into four products for four audiences?*

The answer, grounded in June-2026 research (recorded in §9):

1. **The generic agent chassis is commoditized.** Claude Code / the Agent SDK, opencode, OpenClaw
   (135K+ stars), CrewAI, Microsoft Agent Framework — that layer is a lost race for a solo project
   and a pointless one: it is not where Ludwig's value lives.
2. **The value lives below the chassis:** the deterministic critic, the exact B-rep, the
   conventions (`standards.yaml`), the derived drawings, and the pre-export gate. No competitor
   couples these (Zoo: proprietary kernel, unverified generation; Adam: STL/OBJ/SCAD, STEP still
   roadmap; Spectral SGS-1: direct B-rep generation with a quality cliff; DraftAid: drawings only).
3. **Two open standards now exist that let Ludwig plug into every chassis at once:** MCP (tools)
   and Agent Skills / SKILL.md (knowledge, agentskills.io, Agentic AI Foundation, ~40 products).

So: **expose three surfaces, build zero chassis.**

## 1. The three surfaces (the whole strategy in one table)

| Surface | What it is | What it makes true |
|---|---|---|
| **S-MCP** | `ludwig mcp` — an MCP server exposing `compile / plan / build / verify / edit / section / export` over the daemon | Every harness (Claude Code, opencode, Claude Desktop, OpenClaw, Copilot…) becomes a Ludwig frontend. "Fully agentic AI-first" becomes literally true on day one. |
| **S-PACK** | Domain packs in the **Agent Skills** format: a folder with `SKILL.md` + a `standards.yaml` fragment + a critic module + toolkit ops | "Artists, architects, builders, 3D printers" become **packs, not products**. One engine, N domains — this is **[H7] productized**: S9 proved one IR serves fab + BIM; packs are the mechanism that keeps that true as domains multiply. Packs work inside Ludwig's own loop AND inside any external harness driving Ludwig over MCP. |
| **S-MEM** | Two new memory stores: the **precedent store** (FTS5 over past programs/parts → codegen context) and the **repair corpus** (critic-failure→fix pairs → repair prompts) | Memory defined as *things that move the [H6] pass-rate number*, nothing else. |

**Ordering (LOCKED): S-MCP → S-MEM → S-PACK.** MCP first because it is the cheapest build (a thin
wrapper over `webapp/service.py`), the loudest demo ("Claude Code designed and exported a
critic-verified precast panel through Ludwig"), and it settles Ludwig-as-tool before
Ludwig-as-platform. Memory second because it compounds every subsequent pack. Packs third because
the pack format should be extracted from a *working* second domain, not designed speculatively
(first principle #7).

## 2. New first principles (append to BRIEF §2 — LOCKED)

9. **Ludwig is a tool before it is a platform.** External agents drive Ludwig through the same
   contract the Studio uses. We never fork a "for agents" API from the "for humans" API — one
   daemon, one Op schema, many clients.
10. **The Op-API is the only agent-facing write surface.** Anything an external agent asks Ludwig
    to do arrives as validated data (ops, params, briefs) — never as code to execute. The 2026
    ClawHub incident (1,184 malicious skills: backdoors, credential stealers, malware) is the
    standing proof of principle #6; MCP does not relax it, it operationalizes it.
11. **Packs are first-party and signed into the repo.** A pack = SKILL.md + standards fragment +
    critic + ops. Third-party packs are out of scope until a review/signing gateway exists
    (the Agora "customs office" model). No marketplace.
12. **Memory earns its bytes.** A memory store exists only if a frozen-set eval shows it moves
    first-pass pass-rate, repair rounds, or token cost. No vector DB until FTS5 measurably fails.

## 3. Target architecture (the frame)

```
 CLIENTS       Studio (three.js) · CLI · macOS shell (Tauri) · Claude Code / opencode / any harness
                          │                                        │
 CONTRACT      versioned HTTP+SSE (Op schema, result payload)   MCP tools (stdio + HTTP)
                          └──────────────┬─────────────────────────┘
 HARNESS       ludwigd — loop · Op-API · permissions · plan-mode · pre-export critic hook
               inference: thin BYO-CLI seam (claude | opencode | local)   [H5 unchanged]
 KNOWLEDGE     packs = Agent Skills folders (SKILL.md + standards fragment + critic + ops)
               memory = standards.yaml · precedent store (SQLite FTS5) · repair corpus
 ENGINE        IR · DAG evaluator · critic panel · CadQuery/OCCT · sketch solver (planegcs seam)
 BACKENDS      STEP · IFC · DXF/shop-drawing · section · render · present · (STL, A-series)
```

Everything below the CONTRACT line exists. The A-series builds the contract's second face (MCP),
the KNOWLEDGE row's two new stores, and the first pack.

### 3.1 `ludwigd` — formalizing the daemon
`webapp/server.py` + `service.py` **is** the daemon; the A-series names it and hardens the
contract, it does not rewrite it. Rules:
- The JSON contract (op schema, result payload, SSE event shapes) gets a `schema_version` field
  and a `docs/CONTRACT.md` page. Breaking a shape = version bump + one release of dual support.
- The stdlib server stays for local use (dependency-light — a virtue). **FastAPI migration is
  gated on the hosted API tier becoming real** (GTM.md), not before. When it happens, pydantic
  models mirror the Op dataclasses and the OpenAPI schema doubles as MCP tool documentation.
- The per-session artifact namespacing already shipped for the public demo is the seed of
  multi-tenancy — extend it, never parallel-build it.

### 3.2 The MCP server (S-MCP)
- **Transport:** stdio first (the `claude mcp add ludwig -- ludwig mcp` path), HTTP second
  (reuses the daemon). One process can serve both.
- **Tool surface (v1, deliberately small):**
  `ludwig_compile(brief) → result`, `ludwig_plan(instruction, program) → ops[]`,
  `ludwig_build(program, ops) → result + inverse_ops`, `ludwig_verify(program) → critic report`,
  `ludwig_edit(program, instruction) → diff + result`, `ludwig_section(program, plane) → artifact`,
  `ludwig_export(program, formats) → paths`. Every result carries the critic verdict; **export
  refuses on a failing critic exactly as the CLI does** — the pre-export hook is inside the tool,
  not around it.
- **The trust story is the pitch:** the external agent plans; Ludwig validates and executes.
  Malformed or unknown ops are rejected, never exec'd (`ops.parse_plan`, unchanged). This is what
  "agent writes Blender Python" integrations (BlenderMCP et al.) structurally cannot claim.
- **Inference note:** MCP tool calls are token-free on Ludwig's side — the *caller's* model does
  the reasoning. This extends the BYO-inference economics: when Claude Code drives Ludwig, we run
  zero inference at all.

### 3.3 Memory (S-MEM) — two stores, both measured
- **Precedent store.** SQLite FTS5 over every compiled program: brief text, element types, named
  dims, pack, critic outcome. At codegen time, retrieve top-k similar precedents and inject the
  winning program(s) as few-shot context. Kill criterion: if pass-rate or repair-rounds on the
  frozen set don't improve, it ships behind a flag, default off.
- **Repair corpus.** Mine (critic-failure JSON → successful fix diff) pairs from every eval and
  live run into `store/`. Inject the nearest failures into `prompts/repair.md` context. This is
  the store most likely to pay: the R-series already proved the critic's exact error signal is
  what closes the 60%→100% gap; giving repair *remembered* fixes compounds it.
- Both stores are local, git-ignorable, and exportable — a team's shared memory later becomes a
  Hosted-tier feature (GTM) without an architecture change.

### 3.4 Packs (S-PACK) — the Agent Skills format
A pack is a directory under `packs/<name>/`:
```
packs/print3d/
  SKILL.md            # frontmatter (name, description) + the domain knowledge itself
  standards.yaml      # fragment, deep-merged over the root standards.yaml
  critic.py           # registers checks via critic.panel.register — no loop change [H4]
  ops.py              # optional toolkit extensions (recorded ops, DAG-expressible)
  briefs.py           # the pack's frozen eval briefs + reference oracle
```
- SKILL.md follows the agentskills.io spec so the *same folder* is loadable by Claude Code,
  opencode, Codex, et al. — the domain knowledge teaches external agents how to drive Ludwig well.
- **First pack (LOCKED): `print3d`.** Rationale: smallest honest delta (STL backend is trivial
  from exact B-rep; printability critic = min-wall per process, overhang angle vs a threshold,
  bed-contact area, bounding volume vs printer envelope from `standards.yaml`), a huge self-serve
  audience, and it stresses the pack format with a *fabrication* domain — the regime our critic is
  strongest in. The artist/render pack stays parked (FINDINGS: noise-limited regime).
- **Second pack candidate: `joinery`** (Profile type, Timmerwerk-adjacent domain knowledge — kozijnen,
  ramen, deuren conventions). Decide after `print3d` proves the format.
- The existing precast/AEC content is retro-fitted into `packs/precast/` and `packs/aec/` **only
  after** two packs exist and the format is stable — extraction, not speculation.

## 4. Short-term plan — the A-series (one session = one PR; `--selftest` stays green, token-free)

*Sequencing note: **D1 (daemon health/shutdown/token — see MACOS_APP_PLAN.md) runs before A2** —
it is a small session that hardens the exact surface the MCP server exposes and unblocks both series.*

**A1 — Contract page + schema_version + plan-of-record repoint.** `docs/CONTRACT.md` documenting
the result payload, Op schema, SSE events; `schema_version` added to every payload. **Update
CLAUDE.md and README:** HARNESS_BRIEF.md joins BRIEF.md as read-first; the A/D-series roadmaps
become the canonical schedule (R1–R34 marked complete/historical, as ROADMAP_SESSIONS was before it).
*Gate:* selftest asserts the version field; contract doc reviewed against live payloads; a fresh
Claude Code session, reading only CLAUDE.md, lands on the correct current plan.

**A2 — MCP server v1 (stdio).** `agent/mcp.py` via the Python MCP SDK, wrapping `service.py`
(compile/verify/export). `cli.py mcp` entry. **The MCP SDK is imported lazily inside `agent/mcp.py`
only** — the CLAUDE.md convention stands: `--selftest` and the pure-Python spine stay green on a
machine without it. *Gate:* from a Claude Code session,
`ludwig_compile("steel bracket 80×40×6, two M8 holes")` returns a passing critic report and a
STEP path; a failing brief returns the critic report and **no** fab file.

**A3 — MCP plan/build/edit + permissions.** Expose the Op-API tools; a `permissions` block in
`standards.yaml` (auto-apply param edits; confirm structural ops; always confirm export) enforced
server-side. *Gate:* an external agent's malformed op is rejected with a structured error, nothing
executed; a valid 3-op plan round-trips with an inverse plan.

**A4 — The demo, the docs, and the second number.** A recorded/reproducible walkthrough: Claude
Code (and opencode, to prove provider-blindness) designs, verifies, and exports a precast panel
through Ludwig MCP. README section + `docs/MCP.md`; GTM.md gains an "MCP as distribution channel"
paragraph. **Build the external-agent pass-rate harness** (`cli.py --eval --mcp`): the frozen
briefs driven through the MCP tools by a scripted external-agent session, reported next to the
native number (§8). *Gate:* a stranger reproduces the demo from the docs in <10 minutes; FINDINGS
records the first external-agent pass-rate and the gap to native.

**A5 — Repair corpus.** Miner over eval/live runs → `store/repairs.sqlite`; nearest-failure
injection into repair prompts. *Gate:* frozen-set eval with corpus on vs off; report the delta in
FINDINGS (ship default-on only if repair rounds or pass-rate improve).

**A6 — Precedent store.** FTS5 index + top-k retrieval into codegen context, flag-gated.
*Gate:* same measure-don't-assert protocol; FINDINGS entry either way.

**A7 — STL backend + `print3d` critic v1.** `backends/stl.py` (tessellation params from
standards); `critic/printability.py` (min-wall per process, overhang vs threshold, envelope,
bed contact), registered per [H4]. *Gate:* a bracket destined for FDM fails on a 0.4 mm wall with
the right message; repair fixes it; STL opens in a slicer.

**A8 — The pack format + `packs/print3d/`.** Pack loader (deep-merge standards, register critic,
extend toolkit, add briefs); SKILL.md written to the agentskills.io spec. *Gate:* `--pack print3d`
changes critic behavior with zero loop changes; the same SKILL.md folder loads in Claude Code and
measurably improves an external agent's first-pass on the print briefs.

**A9 — Pack surfacing in Studio + CLI.** Pack switcher, per-pack critic labels in Ambient
Correctness, `--pack` everywhere. *Gate:* token-free Studio injection shows pack-specific checks.

**A10 — [DECISION SESSION] second pack.** Choose `joinery` vs retro-fitting `precast` based on
A8 findings + any real user signal. Produces the pack, or a documented deferral.

*(A-series runs in parallel with the D-series — docs/MACOS_APP_PLAN.md — which has no code
dependencies on A1–A10 beyond a stable daemon.)*

## 5. Long-term plan (post A-series, held at low resolution per principle #7)

- **L1 — Hosted API tier.** FastAPI migration, auth, metering; "verified DXF/STEP as a service"
  (GTM secondary model). The MCP HTTP transport becomes the same endpoint.
- **L2 — Team memory.** Shared precedent store + shared standards as the Hosted Pro differentiator.
- **L3 — P2-proper (BRIEF §7).** The conventioned drawing engine grows toward the architect
  gate (SpatialElement graph, hierarchical program, IDS+geometry compliance). Packs make this an
  `aec` pack rather than a fork.
- **L4 — Third-party packs, if ever.** Only behind a signing/review gateway (Agora model);
  re-read principle #11 before relitigating.
- **L5 — P4 scale** (hierarchical loop, cascade repair) — unchanged from BRIEF.

## 6. Explicit non-goals (write them down so they stay dead)
- No generic agent chassis, no session-management framework, no bundled inference.
- No artist/render vertical revival until a deterministic critic exists for that regime.
- No vector database, no embeddings service, until FTS5 fails a measured test.
- No WASM/browser kernel port: it forfeits IfcOpenShell, the CadQuery codegen corpus ([H1]'s
  measured bet), and the eval harness. Watch Chili3D / opencascade.js v3 as *signals* that the
  kernel layer is commoditizing — which is the argument for the critic moat, not against it.
- No Electron. No second UI framework. No marketplace.

## 7. Risks and their standing mitigations
- **MCP surface abused as a code path** → the Op-API is the only write surface (principle #10);
  fuzz `parse_plan` in CI.
- **Pack format ossifies too early** → format is extracted at A8 from one real pack, revisited at
  A10 with a second; no format doc is "final" before two packs exist.
- **Memory stores rot into superstition** → every store carries its FINDINGS entry and a kill
  criterion (principle #12).
- **Anthropic/agent-ecosystem churn** (SDK metering changed June 15 2026; standards young) →
  the thin CLI seam and the open MCP/Skills standards are precisely the low-lock-in posture; keep
  the Agent SDK behind the seam as one adapter, never the foundation ([H5]).

## 8. The one tracked number, extended
[H6] stands: first-pass geometric pass-rate on the frozen set, per pack. The A-series adds one
companion number: **external-agent pass-rate** — the same frozen briefs driven through MCP by a
stock Claude Code/opencode session with the pack's SKILL.md loaded. The gap between the two is the
measure of how much of Ludwig's reliability survives being someone else's tool. Closing that gap
is the harness thesis, quantified.

## 9. Decision record (research grounding, June–July 2026)
- Agent Skills open standard: agentskills.io, published 2025-12-18, Agentic AI Foundation; ~40
  compatible products incl. Claude Code, Codex, Copilot, Cursor, Gemini CLI, OpenCode.
- ClawHub supply-chain incident: 1,184 malicious skills found on a public registry → principle #11.
- Agent SDK: Claude-model-shaped; separate metered quota for headless use from 2026-06-15 → [H5] upheld.
- Competitors: Zoo (proprietary kernel, API-first), Adam ($6M seed, STL/OBJ/SCAD, STEP roadmap),
  Spectral SGS-1 (direct B-rep gen, quality cliff on complexity), Leo (PDM retrieval, not
  generation), DraftAid (2D drawing automation — the one to watch near our drawings moat).
- Browser kernels: Chili3D (OCCT→WASM), opencascade.js v3 (bindings retargeted at coding agents)
  → kernel location is commoditizing; the moat is critic + conventions + drawings.
