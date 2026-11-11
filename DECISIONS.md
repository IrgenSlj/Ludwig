# Decisions

One line per decision: date, decision, reason. Newest at the bottom. Reversing a
decision is a new line, not an edit.

- 2026-11-11 — Ludwig becomes a pre-production check for fabricators; generation, the Studio, the desktop app and the MCP server are dropped. Reason: generation and reviewer-side drawing review are crowded; the fabricator side with structured data is not.
- 2026-11-11 — Continue in the existing repository; old code removed in one commit and kept at tag `harness-era-v1`. Reason: keep history and the project name.
- 2026-11-11 — First trade is joinery; first pack is `joinery-nl`. Reason: founder's daily domain.
- 2026-11-11 — Development uses public samples and invented fixtures only. Reason: no agreement yet to use any company's files.
- 2026-11-11 — First ERP adapter is a generic CSV/Excel importer with a mapping file. Reason: the target production software is not yet named.
- 2026-11-11 — All four input families are in scope (IFC, DXF/DWG, PDF, schedules), built in the order IFC and schedules, then DXF and PDF. Reason: all are common in practice; structured inputs give value soonest.
- 2026-11-11 — Verdicts are deterministic; LLM use is confined to `ludwig.assist`. Reason: published benchmarks show vision models unreliable on door and window symbols, and a work preparer must be able to trust a blocker.
- 2026-11-11 — Rules are data: IDS for required information, YAML with a small expression language for computed and cross-source checks. Reason: safe to accept packs from customers; reuse of an open standard.
- 2026-11-11 — Python 3.12, single package `ludwig` under `src/`. Reason: best IFC library; fixes the old top-level package name collisions.
- 2026-11-11 — No GPL or AGPL libraries in-process; pdfplumber instead of PyMuPDF; DWG via an external converter. Reason: the product will be sold closed-source.
- 2026-11-11 — CadQuery/OCCT geometry is not a dependency. Reason: first-trade checks are about attributes and dimensions, not solids. Revisit only if a rule needs it.
- 2026-11-11 — The files ARCHITECTURE section 6 keeps live in `reference/`, outside any package and excluded from lint, and each is deleted when the task that uses it lands. Reason: keeping them at their old paths would leave the old top-level packages (`agent`, `critic`, `toolkit`, `webapp`) in place.
- 2026-11-11 — Dev dependencies: pytest (MIT) and ruff (MIT). Reason: CI gate. Neither ships with the product.
