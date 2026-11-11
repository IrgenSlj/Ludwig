# Ludwig

A pre-production check for building-component fabricators, starting with joinery (windows, doors, frames).

Ludwig reads the architect's documents (IFC, schedules, DXF, vector PDF) and the factory's own production export,
puts both into one element table, and runs deterministic rule packs over it. It reports mismatches between the two
and breaches of the factory's limits, with the source of every value, before anything is cut.

    pip install -e ".[dev]"
    ludwig check --architect <model.ifc> <schedule.xlsx> --pack packs/joinery-nl --out report/
    # --erp <file> --mapping <file> arrives in phase 2

Status and plan: [PLAN.md](PLAN.md). Specification: [docs/SPEC.md](docs/SPEC.md). Earlier versions: tag `harness-era-v1`.
