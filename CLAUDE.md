# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Ludwig is

A pre-production check for building-component fabricators, starting with joinery
(windows, doors, frames). It reads the architect's documents and the factory's own
production data, puts both into one element table, and runs deterministic rules over
it. It reports mismatches and rule breaches before anything is cut.

It is not a CAD tool, not a generator and not a drawing viewer.

## Read before every session

1. `PLAN.md` — phases, tasks and gates. Work only on the current phase.
2. `docs/SPEC.md` — data model, rule format, finding format.
3. `docs/ARCHITECTURE.md` — module boundaries.
4. `DECISIONS.md` — what has been decided and why.

## How to work

- Read the Status line at the top of `PLAN.md` first. Take the first unchecked task that is
  not marked **(Irgen)**, not **Deferred** and not waiting on a person. Do that task only.
  If none is open, say so and stop.
- One task per commit. Tick the task in `PLAN.md` in the same commit.
- Never start a later phase. If a task seems to need later-phase work, stop and say so.
- If the spec is silent or contradicts itself, stop and ask. Do not guess and continue.
- When a decision is made, add one dated line to `DECISIONS.md`.

## Hard rules

1. **Deterministic verdicts.** No LLM call may produce, change or suppress a finding.
   LLM use is limited to the `ludwig.assist` module (see SPEC section 9).
2. **Never pass silently.** If a rule cannot be evaluated because data is missing, the
   result is `not_checked` with the reason. It is never `pass`.
3. **Every rule has two fixtures**: one that passes and one that fails. A rule without
   both does not get merged.
4. **Packs are data.** No Python, no `eval`, no `exec`, no imports in rule packs. The
   expression language in SPEC section 6 is the only way to compute.
5. **Evidence on every finding.** Each finding points to where the value came from
   (file, and IFC GlobalId, DXF handle, sheet cell or PDF page and box).
6. **Millimetres everywhere.** Convert at the parser boundary. Store numbers, not strings.
7. **No real customer or employer data in the repository.** Fixtures are public samples
   or invented. Record the source and licence of each sample in `fixtures/README.md`.
8. **No new dependency** without a line in `DECISIONS.md` stating its licence. Closed
   product: no GPL or AGPL libraries in-process (this rules out PyMuPDF and LibreDWG).
9. **Parsers never raise on bad input.** They return what they could read plus a list of
   parse warnings, which the report shows.

## Layout

```
src/ludwig/
  model.py        # Element, SourceRef, Finding, Match
  check.py        # one check end to end; used by cli.py and api/
  parsers/        # ifc.py, schedule.py, dxf.py, pdf.py, tables.py, values.py (unit/number
                  # coercion), columns.py (mapping proposals), mappings/ (defaults,
                  # column_names.yaml)
  adapters/       # erp_table.py (generic CSV/Excel + mapping)
  match.py        # pairs architect elements with ERP elements
  rules/          # expr.py (language), engine.py, ids.py, packs.py, limits.py, fixtures.py,
                  # install.py (pack upgrades keeping factory limits)
  report/         # json.py, excel.py, bcf.py, pdf_markup.py
  assist/         # provider.py, drafts.py; the only place an LLM may be called
                  # (off unless LUDWIG_ASSIST_COMMAND)
  cli.py          # `ludwig check`, `ludwig serve`
  api/            # FastAPI service: app.py, db.py (+ migrations/, Alembic), jobs.py, storage.py,
                  # guards.py, settings.py, auth.py (logins), activity.py, data.py (delete,
                  # export, retention)
packs/joinery-nl/ # pack.yaml, checks.yaml, limits.yaml, fixtures/<rule>/pass|fail.json
mappings/examples/# office mapping starting points
fixtures/         # shared sample inputs (public or invented; see fixtures/README.md)
tools/            # make_duplex_2d.py (regenerates invented 2D fixtures), minipdf.py
web/              # React + TypeScript web app (Vite)
tests/            # pytest; tests/packs/ (demo, reconcile) engine test packs, tests/ids/ IDS files,
                  # test_gate_phaseN.py are the end-to-end gate checks from PLAN.md
docs/             # SPEC, ARCHITECTURE, ERROR_CATALOGUE (+ ERROR_CANDIDATES), ERP_SYSTEMS, DWG,
                  # INSTALL, HOSTING
Dockerfile        # image: service + web app + released packs (on site, and for deploy/)
deploy/           # hosted kit per factory: compose.yaml, Caddyfile, backup.sh, restore.sh
```

## Commands

```
pip install -e ".[dev,api]"
ruff check
pytest                                          # set LUDWIG_TEST_DATABASE_URL to also hit Postgres
pytest tests/test_expr.py::test_name            # one test; -k <expr> to filter
pytest tests/test_pack_joinery_nl.py            # pack fixtures + clean duplex end to end
cd web && npm ci && npm run typecheck && npm test && npm run build
ludwig check --architect <files...> [--erp <file> --mapping <file>] --pack packs/joinery-nl --out report/
LUDWIG_WEB_DIR=web/dist ludwig serve           # service + web app
ludwig user add <name> --admin                  # first admin; from then on everyone signs in
cd deploy && docker compose up -d --build       # hosted instance (docs/HOSTING.md)
```

Service settings are `LUDWIG_*` environment variables, all listed in `api/settings.py`.

CI (`.github/workflows/`) runs ruff, pytest on SQLite, `pytest tests/test_api.py` against
Postgres 16, the web checks, and a Docker image build.

## How a check flows

`check.run()` is the single pipeline; the CLI and `api/jobs.py` both call it.

1. `read_architect()` dispatches by extension to `parsers/`. Schedules (.xlsx/.csv/.pdf) need
   `<name>.mapping.yaml` beside them; for IFC and DXF an office mapping is optional. DWG is
   rejected with a pointer to `docs/DWG.md` (convert to DXF; LibreDWG is GPL).
2. `read_erp()` reads the factory export through `adapters/erp_table.py`; its mapping is
   `--mapping` or `<name>.mapping.yaml` beside it.
3. All `Element`s go into one table, told apart by `side` (architect or erp); `sources`
   carries the evidence. `match.pairs()` pairs the two sides by mark, falling back to size
   within the pack's `match_tolerance_mm`. With no ERP elements it returns `None` and every
   compare rule is `not_checked` (by design, hard rule 2).
4. `rules/engine.run()` evaluates the pack's `checks.yaml` (expressions via `rules/expr.py`,
   limits via `rules/limits.py`); IDS specs in the pack run through `rules/ids.py`.
5. `write_reports()` writes `report.json`, `report.xlsx`, `report.bcf` and marked PDFs.

## Adding a rule

1. Add an entry to `packs/<pack>/checks.yaml` (format: SPEC section 6). `kind` is one of
   `compare`, `require`, `unmatched`, `consistent`; unknown keys are a load error. Put
   numbers in `limits.yaml` and refer to them as `limits.<group>.<name>`.
2. Add `packs/<pack>/fixtures/<rule id>/pass.json` and `fail.json`, each
   `{"elements": [{"side", "type", "mark", "props"}, ...]}`.
3. `pytest tests/test_pack_joinery_nl.py` runs `rules/fixtures.check()` over every rule.

## Definition of done for a task

- The acceptance line in `PLAN.md` is met and covered by a test.
- `ruff check` and `pytest` pass.
- No hard rule above is broken.
- Public functions have type hints and a one-line docstring.

## Style

- Python 3.12, standard library first, small modules, dataclasses for the model.
- Plain names. No abstractions for a second use case that does not exist yet.
- Comments say why, not what. No history or narrative in comments.
- User-facing messages are short, in English for now, with the value, the limit and the
  element mark. Keep message templates in the pack so they can be translated later.

## Legacy code

Everything from the earlier design-harness version was removed in the reset commit and
is recoverable at the tag `harness-era-v1`. Do not restore any of it without a decision
in `DECISIONS.md`.
