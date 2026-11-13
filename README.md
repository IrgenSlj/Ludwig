# Ludwig

A pre-production check for building-component fabricators, starting with joinery (windows, doors, frames).

Ludwig reads the architect's documents (IFC, schedules, DXF, vector PDF) and the factory's own production export,
puts both into one element table, and runs deterministic rule packs over it. It reports mismatches between the two
and breaches of the factory's limits, with the source of every value, before anything is cut.

Command line:

    pip install -e ".[dev]"
    ludwig check --architect model.ifc schedule.csv --erp export.csv --pack packs/joinery-nl --out report/

Each schedule or export needs a column mapping `<name>.mapping.yaml` beside it (examples in `fixtures/` and
`mappings/examples/`). The report folder gets `report.json`, `report.xlsx`, `report.bcf` and marked copies of PDFs.

Service and web app (or the Docker image, see [docs/INSTALL.md](docs/INSTALL.md)):

    pip install -e ".[api]"
    (cd web && npm ci && npm run build)
    LUDWIG_WEB_DIR=web/dist ludwig serve      # http://127.0.0.1:8000

Status and plan: [PLAN.md](PLAN.md). Specification: [docs/SPEC.md](docs/SPEC.md). Decisions: [DECISIONS.md](DECISIONS.md).
Earlier versions: tag `harness-era-v1`.
