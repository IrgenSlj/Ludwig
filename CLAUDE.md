# CLAUDE.md — working rules for Ludwig

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

- Take the first unchecked task in the current phase of `PLAN.md`. Do that task only.
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
  parsers/        # ifc.py, schedule.py, dxf.py, pdf.py, tables.py, mappings/ (defaults)
  adapters/       # erp_table.py (generic CSV/Excel + mapping)
  match.py        # pairs architect elements with ERP elements
  rules/          # expr.py (language), engine.py, ids.py, packs.py, limits.py, fixtures.py
  report/         # json.py, excel.py, bcf.py, pdf_markup.py
  assist/         # the only place an LLM may be called (off unless LUDWIG_ASSIST_COMMAND)
  cli.py          # `ludwig check`, `ludwig serve`
  api/            # FastAPI service: app.py, db.py, jobs.py, storage.py, guards.py
packs/joinery-nl/ # pack.yaml, checks.yaml, limits.yaml, fixtures/<rule>/pass|fail.json
mappings/examples/# office mapping starting points
fixtures/         # shared sample inputs (public or invented; see fixtures/README.md)
tools/            # make_duplex_2d.py (regenerates invented 2D fixtures), minipdf.py
web/              # React + TypeScript web app (Vite)
tests/            # pytest; tests/packs/ hold engine test packs
docs/             # SPEC, ARCHITECTURE, ERROR_CATALOGUE, DWG, INSTALL
Dockerfile        # on-site image: service + web app + packs
```

## Commands

```
pip install -e ".[dev,api]"
ruff check
pytest                                          # set LUDWIG_TEST_DATABASE_URL to also hit Postgres
cd web && npm ci && npm run typecheck && npm test && npm run build
ludwig check --architect <files...> [--erp <file> --mapping <file>] --pack packs/joinery-nl --out report/
LUDWIG_WEB_DIR=web/dist ludwig serve           # service + web app; settings from LUDWIG_* env
```

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
