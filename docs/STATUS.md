# Ludwig — status & plan of record (living)

*The one-page "where are we, what's next." The specs are [BRIEF.md](../BRIEF.md) (founding) +
[HARNESS_BRIEF.md](../HARNESS_BRIEF.md) (A-series) + [docs/MACOS_APP_PLAN.md](MACOS_APP_PLAN.md) (D-series) +
[docs/DESIGN_BRIEF_STUDIO_V2.md](DESIGN_BRIEF_STUDIO_V2.md) (Studio v2). This file tracks execution against
them. Update it as sessions land. Last updated 2026-07-06.*

## v2 direction (M0 audit landed 2026-07-06)
[LUDWIG_V2_BRIEF.md](../LUDWIG_V2_BRIEF.md) ("the deliberative harness") was audited against reality in
**[docs/AUDIT_NOTES.md](AUDIT_NOTES.md)** — it assumes a Blender substrate + VLM critic Ludwig doesn't have.
**Decision: Option A — retrofit only the substrate-agnostic wins onto the CadQuery/OCCT core** (keep the
deterministic critic; no Blender, no VLM judge, no BlenderGym). First slice: **WS2 deliberative
branch-and-prune search** (deterministic critic = free pruner). Strong follow-on: **WS7 telemetry/trajectory
dataset**. Rejected workstreams and the full transfer table are in AUDIT_NOTES §3–5.

## B-series direction (competitive review landed 2026-08-04)
**[docs/BENCH_PLAN.md](BENCH_PLAN.md)** — a technology review of Autodesk / PTC-Onshape / Zoo / the DFM
category produced two findings that set the current workstream. (1) **The MCP surface is commodity**:
Autodesk shipped Fusion MCP with Anthropic (Apr 2026) and a Revit public MCP; PTC shipped an Onshape MCP
toolkit (Jul 2026). Nobody ships a deterministic verifier — the differentiator moves from *"we have MCP"*
to **"we are the verifier"**. (2) **Our tracked number is measured on a set we wrote ourselves.** So:
**B1** BenchCAD `edit-bench` harness + oracle-validated grader · **B2** verify foreign geometry ·
**B3** the live number · **B4** capability to-do from the failures · **B5** `ludwig_query` (stretch).

## Tracked numbers ([H6])
- **First-pass geometric pass-rate** (frozen set, `cli.py --eval --live`): ~93% first-pass · 100% post-repair.
- **BenchCAD edit-bench** (third-party, `cli.py --eval --bench edit [--live]`): grader **oracle-validated**
  at n=100 (ground-truth 1.000 · unedited 0.000 · exec 100% over 96 gradeable rows, 4 ungradeable named).
  Live number: see FINDINGS §B3. Published comparison: GPT-5.3 (thinking) 0.865 normalized accuracy.
- **External-agent pass-rate** (`cli.py --eval --mcp`, A4 companion): **93% (14/15)** — an external agent
  driving Ludwig over MCP matches the native first-pass rate; **the gap to native is 0** (§8 thesis
  quantified). Harness now robust to inference throttling (paces + retries throttle-shaped fails only); the
  clean run needed zero retries. Lone miss = `stair_flight`, a genuine n=1 codegen miss, not an artifact.

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
- **A4** — the demo, the docs, the second number. **Runnable** walkthrough (`examples/mcp_walkthrough.py`)
  drives the real stdio server through the whole trust arc (verify → build+inverse → reject a `rm -rf /` op
  → critic catches a 0.5 mm wall → export refused → confirmed export writes STEP), asserting each invariant,
  token-free. `docs/MCP.md` leads with the one command. `--eval --mcp` hardened against throttling →
  **external-agent pass-rate 93% (14/15), gap-to-native 0** (FINDINGS). GTM motion in `docs/GTM.md`.
  Public-demo runtime **verified** end-to-end (DEPLOY.md); deploy needs only cloud creds.
- **A5 (infra)** — repair corpus (`store/repairs.py`): remembered (critic-failure→fix) pairs, mined from
  `eval/pool.py` (disjoint from the frozen set), injected into the repair prompt. Flag-gated
  `memory.repair_corpus`, **default OFF and UNMEASURED** — it flips default-on only if an on/off eval moves
  repair rounds/rate (the measurement is Tier-1 below). `cli.py --mine-repairs` builds it.
- **A7** — STL backend + printability critic (the print3d fabrication wedge). `backends/stl.py` emits a
  watertight binary STL (critic-gated like STEP); `critic/printability.py` runs only for a print `process`
  (fdm/sla, else N/A) and gates on min-wall + build envelope while advising on overhang + bed-contact
  (`geometry.print_mesh_stats`). Thresholds in `standards.yaml: printing`. Addable per [H4], no loop change.
- **Critic hardening** — the dimensional check self-verifies registered extents when a brief declares no dims
  (green instead of a vacuous n/a), and now verifies a **cylinder's diameter** and a **panel's thickness**
  against the measured solid (not just their registered value) — closing two real holes.
- **B1** — BenchCAD `edit-bench` harness (`eval/benchcad.py` + `eval/editbench.py`,
  `cli.py --eval --bench edit`): the third-party number. Family-stratified sampling, a foreign-program
  adapter (BenchCAD assigns `result`/`show_object`; `agent.loop.execute` requires `element` — the two
  trust paths stay separate), exact-boolean IoU, and the minimal-diff ratio nobody else reports.
  **Gate: the grader validates against its own oracle before any token is spent** — it caught three real
  defects at n=100 (FINDINGS §B1). Dev-only path; the AST tripwire on third-party programs is documented
  as a tripwire, not a sandbox.
- **B2** — verify geometry Ludwig did NOT author: `cli.py --verify-file <model.step> [--process fdm|sla]`
  + the `ludwig_verify_file` MCP tool + `service.verify_file_to_result`. The solid-only critics run for
  real; the dimensional critic reports n/a instead of vacuum-passing. This is the "we are the verifier"
  wedge, and it makes Ludwig complementary to Fusion MCP / Onshape / Zoo rather than competing with them.
- **Cleanup** — deleted the inert Blender render backend (`backends/render*`, ~535 lines) and the unwired
  `store/db.py` stub (both recoverable at `mesh-era-m4`); halved MCP export latency (single execute+verify);
  removed 4 dead `standards.yaml` keys; de-duped the diff/repair-hint helpers. Selftest **96/96**.

## Remaining plan — prioritized by leverage (one session = one PR; `--selftest` green, token-free)
*Ordered by value toward the north-star (deploy → distribution → revenue), not strict roadmap sequence.
Each item: why-now · gate. Pick the top unblocked item each session. Specs stay BRIEF/HARNESS_BRIEF/MACOS.*

### Tier 0 — needs the human (unblocks everything downstream)
- **Deploy the public demo.** Runtime is verified (DEPLOY.md); only cloud creds are missing.
  `gcloud run deploy ludwig-demo --source . --region europe-west1 --memory 2Gi --allow-unauthenticated`.
  THE traffic unlock — the demo-led GTM motion can't start without a URL.
- **5–10 ICP intros** (mechanical/hardware). The proof sheet + the runnable MCP walkthrough support outreach.

### Tier 1 — close the open loops (do first; mostly token-bounded)
- **A5 measurement.** `cli.py --mine-repairs` seeds `store/repairs.sqlite` from the pool; then
  `--eval --live --repair` with `LUDWIG_REPAIR_CORPUS=on` vs `off`. Record avg repair rounds + post-repair
  rate in FINDINGS; flip `memory.repair_corpus` default only if it moves a number. *Gate:* honest on/off delta.
- **Foreign-hand shared-daemon seam** (the last honest deferral, design brief §1.1). The stdio MCP server is
  a separate process from the Studio's HTTP daemon, so an external agent's ops can't paint in the Studio
  Activity Rail. MCP-over-HTTP (reuse the daemon) or a stdio→daemon proxy; SSE events gain a `client` field.
  *Gate:* an op driven over MCP appears in the Studio rail tagged by client.

### Tier 2 — the biggest new-audience capability (token-cheap, high visible value)
- **A7 — STL backend + `critic/printability.py`** — **SHIPPED** (see Shipped above): min-wall + envelope gate,
  overhang + bed-contact advise, N/A off a print process; watertight STL, critic-gated. Opens the 3D-print
  self-serve wedge. *Remaining nice-to-have:* a `process`-carrying print eval brief set + a live repair demo
  (thin wall → repair thickens → passes) once inference budget allows.
- **A8 — pack format + `packs/print3d/`.** Extract the Agent-Skills pack format from the *working* print
  domain (SKILL.md to agentskills.io spec; loader deep-merges standards, registers the critic, adds briefs —
  no loop change). *Gate:* `--pack print3d` changes critic behavior with zero loop changes; the same folder
  loads in Claude Code and lifts an external agent's first-pass on print briefs.

### Tier 3 — deepen the core + surface the packs
- **A6 — precedent store** (FTS5 over past programs → top-k few-shot into codegen, flag-gated). The lever for
  the *first-pass* number (A5 was for repair). Payload gains `precedents[]` (unblocks the Studio "informed by"
  line). *Gate:* measured first-pass delta; FINDINGS either way.
- **A9 — pack surfacing** in Studio (the deferred pack-indicator slot) + CLI `--pack`; per-pack Ambient labels.
- **A10 — [decision] second pack:** `joinery` (kozijnen/ramen/deuren) vs retro-fit `precast`, from A8 findings.

### Tier 4 — the signed desktop app (D-series; parallel, only needs a stable daemon)
- **D2** PyInstaller onedir daemon (pinned CPython) · **D3** Tauri shell (spawn onedir, ephemeral port+token,
  splash, reap; Studio forwards the token) · **D4** external-tool detection + honest no-model state · **D5**
  sign+notarize in CI · **D6** macOS chrome (menu bar, ⌘1–4, native dialogs, theme auto-switch) · **D7**
  updater + v0.2.0.

### Housekeeping (fold into whichever session touches the area)
- Fold fresh-compile into the Studio ⌘K intent bar (via `/api/compile_stream`), then retire
  `webapp/index.html` (demoted to `/index.html`).
- *(A4 nice-to-haves)* an opencode cross-provider `--eval --mcp` run (proves provider-blindness) + an
  asciinema/GIF of `examples/mcp_walkthrough.py` for GTM.

## Working conventions (don't relitigate)
- Ship to `main` directly (one deliverable per commit), push often, `--selftest` green every step.
- Real kernel gate needs the venv: `.venv/bin/python cli.py --selftest` (~96 checks) and `pytest`.
- MCP needs the SDK (`pip install mcp`); imported lazily so the spine stays green without it.
- Measure, don't assert — every store/claim gets a FINDINGS entry + a kill criterion.
