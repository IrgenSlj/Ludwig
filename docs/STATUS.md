# Ludwig — status & plan of record (living)

*The one-page "where are we, what's next." The specs are [BRIEF.md](../BRIEF.md) (founding) +
[HARNESS_BRIEF.md](../HARNESS_BRIEF.md) (A-series) + [docs/MACOS_APP_PLAN.md](MACOS_APP_PLAN.md) (D-series) +
[docs/DESIGN_BRIEF_STUDIO_V2.md](DESIGN_BRIEF_STUDIO_V2.md) (Studio v2). This file tracks execution against
them. Update it as sessions land. Last updated 2026-07-04.*

## Tracked numbers ([H6])
- **First-pass geometric pass-rate** (frozen set, `cli.py --eval --live`): ~93% first-pass · 100% post-repair.
- **External-agent pass-rate** (`cli.py --eval --mcp`, A4 companion): harness built; a clean full-set number
  is **pending a non-throttled inference run** (the first run was rate-limited mid-batch — see FINDINGS).

## Shipped (post-R34; R1–R34 = the complete/historical interaction core)
- **A1** — versioned wire contract: `schema_version` on every payload + `docs/CONTRACT.md`; plan-of-record repointed.
- **D1** — daemon hardening for embedding: `/api/health`, `/api/shutdown`, `--port 0` (ephemeral, prints `PORT=`),
  loopback `--token` guarding `/api/*`+`/out/*` (open by default).
- **Studio v2** — cockpit → viewfinder reskin (`webapp/studio.html`): full-bleed Stage, floating glass panels,
  ⌘K intent bar, two themes, permission dial. Engine wiring unchanged. `prototype/` retired; `/` serves the Studio.
- **A2** — MCP server (`cli.py mcp`, `agent/mcp.py`): `ludwig_compile`/`verify`/`build`/`export`. Gate met (real
  client compiled a verified bracket → STEP).
- **A3** — Op-API over MCP + the permission gate (`agent/permissions.py`, `standards.yaml: permissions`,
  `/api/permissions` + the Studio dial). Headless-correct ("confirm" = explicit re-call). Enforced in the one
  shared write path (`build_from_ops`).
- **A4 (partial)** — `docs/MCP.md` (harness walkthrough) + GTM motion + the `--eval --mcp` harness (with
  per-brief failure reasons). **Remaining:** the clean full-set number + the reproducible demo doc/recording.
- **Cleanup** — removed `docs/ROADMAP_SESSIONS.md` + empty dirs; refreshed README/CHANGELOG/CLAUDE/eval docs.

## The one honest deferral
- **Foreign-hand plan card + cross-client Activity Rail** (design brief §1.1) — needs a **shared-daemon seam**
  (the stdio MCP server is a separate process from the Studio's HTTP daemon; foreign ops can't reach the Studio
  rail). Tracked as its own task; do before/with A4's demo. The permission dial + Op-API gate already shipped.

## Remaining plan (one session = one PR; `--selftest` stays green, token-free)
**A-series (S-MCP done → S-MEM → S-PACK):**
- Shared-daemon seam (foreign-hand unblocker) — MCP-over-HTTP or stdio→daemon proxy; SSE events gain a `client` field.
- **A4** finish — clean `--eval --mcp` number (non-throttled) + reproducible demo (Claude Code + opencode) + FINDINGS gap.
- **A5** — repair corpus (`store/repairs.sqlite`, nearest-failure injection); measure on/off; ship default-on only if it moves the number.
- **A6** — precedent store (FTS5, top-k into codegen, flag-gated); result payload gains `precedents[]` (unblocks the Studio "informed by" line).
- **A7** — STL backend + `critic/printability.py` (min-wall/overhang/envelope/bed-contact).
- **A8** — pack format + `packs/print3d/` (SKILL.md to agentskills.io spec; loader deep-merges standards, registers critic, no loop change).
- **A9** — pack surfacing in Studio (the deferred pack-indicator slot) + CLI `--pack`; per-pack Ambient Correctness labels.
- **A10** — [decision] second pack: `joinery` vs retro-fit `precast`.

**D-series (parallel; only needs a stable daemon):**
- **D2** PyInstaller onedir daemon (pinned CPython) · **D3** Tauri shell integration (spawn onedir, ephemeral port+token, splash, reap; Studio forwards the token) · **D4** external-tool detection + honest no-model state (`/api/health` `tools`) · **D5** sign+notarize in CI · **D6** macOS chrome pass (menu bar, ⌘1–4, native dialogs, theme auto-switch) · **D7** updater + v0.2.0 (+ D8 buffer).

**Housekeeping:**
- Fold fresh-compile into the Studio intent bar (via `/api/compile_stream`), then retire `webapp/index.html` (currently demoted to `/index.html`).

## Working conventions (don't relitigate)
- Ship to `main` directly (one deliverable per commit), push often, `--selftest` green every step.
- Real kernel gate needs the venv: `.venv/bin/python cli.py --selftest` (76+ kernel checks) and `pytest`.
- MCP needs the SDK (`pip install mcp`); imported lazily so the spine stays green without it.
- Measure, don't assert — every store/claim gets a FINDINGS entry + a kill criterion.
