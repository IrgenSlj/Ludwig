# Ludwig — development plan

Status: phase 0 done except 0.5–0.6 (Irgen); phase 1 done except 1.7 (waits for the catalogue); phase 2 gate met on invented data, 2.1 open until a real export is mapped; phase 3 gate met; phase 4 tasks done, gate needs a person to open the BCF in two viewers.

Each phase ends in a gate. A phase is finished only when its gate is met. Tasks marked
**(Irgen)** need a person and cannot be done by Claude Code.

## Phase 0 — Reset and evidence

Goal: a clean repository and a written list of the errors worth catching.

- [x] 0.1 Tag the current `main` as `harness-era-v1`.
- [x] 0.2 Remove the old code and documents in one commit. Keep only what the table in
      `docs/ARCHITECTURE.md` section 6 lists as reusable, plus `LICENSE` and `NOTICE`.
- [x] 0.3 Create the `src/ludwig/` layout from `CLAUDE.md`, a new `pyproject.toml`
      (one package named `ludwig`, extras `dev`), and CI running `ruff check` and `pytest`
      on Python 3.12.
- [x] 0.4 Add `CLAUDE.md`, `PLAN.md`, `DECISIONS.md`, `docs/SPEC.md`,
      `docs/ARCHITECTURE.md`. Rewrite `README.md` to ten lines describing the new product.
- [ ] 0.5 **(Irgen)** Write `docs/ERROR_CATALOGUE.md`: at least 20 error types seen in
      practice between architect documents and production. For each: what went wrong,
      which document held the truth, what data would have revealed it, rough cost. No
      company names, project names or real files.
- [ ] 0.6 **(Irgen)** Mark each catalogue entry as catchable from files alone, catchable
      with ERP data, or not catchable.
- [x] 0.7 Collect public sample inputs into `fixtures/`: two IFC models containing
      windows and doors, one DXF with door or window blocks, one schedule in Excel.
      Record source and licence in `fixtures/README.md`.

Gate: at least 10 catalogue entries are catchable from files or ERP data. If fewer,
stop and reconsider the product before writing code.

## Phase 1 — Core engine

Goal: `ludwig check` runs on an IFC model and an Excel schedule and produces a report.

- [x] 1.1 `model.py`: `Element`, `SourceRef`, `Finding` as in SPEC sections 3 and 7.
      Acceptance: round-trips to and from JSON.
- [x] 1.2 `parsers/ifc.py`: read `IfcWindow`, `IfcDoor` and their types into elements
      (mark, overall width and height, quantity by mark, property sets into `props`).
      Acceptance: both sample models parse; counts match a hand count noted in the test.
- [x] 1.3 `parsers/schedule.py`: read an Excel or CSV schedule using a column mapping
      file. Acceptance: sample schedule parses; a missing column gives a parse warning.
- [x] 1.4 `rules/expr.py`: tokenizer, parser and evaluator for the expression language
      in SPEC section 6. Acceptance: table-driven tests for every operator, missing
      values, and rejection of anything outside the grammar.
- [x] 1.5 `rules/packs.py`: load and validate `pack.yaml`, `checks.yaml`, `limits.yaml`.
      Acceptance: an unknown key or a bad expression fails at load time with file and line.
- [x] 1.6 `rules/engine.py`: run checks over the element table and return findings,
      including `not_checked`. Acceptance: fixture tests per rule.
- [ ] 1.7 First ten rules in `packs/joinery-nl/checks.yaml`, chosen from the error
      catalogue, each with a passing and a failing fixture.
- [x] 1.8 `report/json.py` and `report/excel.py`. Acceptance: Excel has one row per
      finding, sorted by severity, with mark, measured, expected and source.
- [x] 1.9 `cli.py`: `ludwig check` as in `CLAUDE.md`. Exit code 0 with no blockers,
      1 with blockers, 2 on usage error.
- [x] 1.10 Internal consistency rule type: compare the IFC model with the schedule
      (count and dimensions per mark). Acceptance: fixture where the two disagree.

Gate: on the sample set, every seeded error is reported, and the clean samples produce
no blocker findings.

## Phase 2 — Reconciliation with production data

Goal: compare what the architect asked for with what was entered for production.

- [ ] 2.1 **(Irgen)** Name the production software and obtain one export with invented
      or anonymised content, or describe its columns.
- [x] 2.2 `adapters/erp_table.py`: generic CSV/Excel importer driven by `mapping.yaml`
      (column names, units, type vocabulary). Acceptance: sample export parses.
- [x] 2.3 `match.py`: pair architect and ERP elements as in SPEC section 5.
      Acceptance: tests for exact, fallback, unmatched and ambiguous cases.
- [x] 2.4 `compare` rule type in the engine with tolerance. Acceptance: fixtures.
- [x] 2.5 Reconciliation rules: quantity per mark, width, height, opening direction,
      glazing type, fire rating, elements missing on either side.
- [x] 2.6 Report shows both values side by side with both sources.

Gate: one complete invented project (architect files plus ERP export, with ten seeded
mismatches) runs end to end, and all ten are found.

## Phase 3 — Two-dimensional inputs

Goal: work for projects that arrive without a model.

- [x] 3.1 `parsers/dxf.py`: block references with attributes on mapped layers become
      elements; dimensions come from attributes first, block extents second.
- [x] 3.2 Table extraction from DXF (schedules drawn as text and lines).
- [x] 3.3 `parsers/pdf.py`: vector PDF only. Extract text with positions and ruled
      tables (pdfplumber). A page with no vector text gives a parse warning, not a guess.
- [x] 3.4 DWG: document the conversion step (external converter to DXF, run as a
      separate process). No DWG library in-process.
- [x] 3.5 Parser mapping files per office convention (layer names, attribute tags).

Gate: the same invented project, delivered as DXF plus PDF schedule, gives the same
findings as the IFC version.

## Phase 4 — Standards and exchange

- [x] 4.1 `rules/ids.py`: evaluate IDS specifications against the element table for the
      entity, attribute, property, classification and material facets, with value
      restrictions. Acceptance: fixtures per facet; unsupported facets give `not_checked`.
- [x] 4.2 `report/bcf.py`: one topic per blocker and warning, with the element
      reference, so findings open in common model checkers.
- [x] 4.3 `report/pdf_markup.py`: add annotations to a copy of the source PDF at the
      evidence location.
- [x] 4.4 Pack versioning: reports record pack name, version and a content hash.

Gate: findings from one run open correctly as BCF in two different viewers.

## Phase 5 — Product

- [ ] 5.1 `api/`: FastAPI service with projects, uploads, runs and findings; Postgres;
      a background job per run.
- [ ] 5.2 Web app (TypeScript, React): upload, findings list, finding detail with
      source side by side, accept or dismiss with a reason, export.
- [ ] 5.3 Accounts per company; a company sees only its own projects and packs.
- [ ] 5.4 Docker image for on-site installation; EU hosting for the cloud version.
- [ ] 5.5 `assist/`: optional help that drafts rules from specification text and
      explains findings in plain language, within SPEC section 9.
- [ ] 5.6 Limits editor so a factory can maintain `limits.yaml` without a text editor.

Gate: a work preparer who has not seen the tool completes a check unaided.

## Phase 6 — Pilot

- [ ] 6.1 **(Irgen)** Written agreement on data use with each pilot company before any
      real file is loaded.
- [ ] 6.2 **(Irgen)** Three pilot factories; encode each one's limits and ERP mapping.
- [ ] 6.3 Measure per project: findings raised, findings accepted, findings dismissed.
- [ ] 6.4 Price and contract for continued use.

Gate: one pilot company pays to continue.

## Not in scope until a gate says otherwise

Geometry kernels, 3D viewing, scanned drawings, vision models, generating drawings or
models, desktop app, more than one trade, IFC5.
