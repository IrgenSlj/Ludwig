# Ludwig daemon (M0)

A thin local FastAPI service that wraps the existing `ludwig.py` orchestrator and
persists projects / runs / artifacts to SQLite. It does **not** reimplement the loop —
it imports and drives `ludwig.py` unchanged (strangler-fig, see [BRIEF.md](../BRIEF.md) §7).

## Run

```bash
python3 -m venv .venv
./.venv/bin/pip install -r daemon/requirements.txt
./.venv/bin/uvicorn daemon.app:app --reload --port 8765
```

Requires the same things the CLI does for real generation: Blender 5.x and a logged-in
`claude` CLI on `PATH`.

## API (M0)

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | daemon + Blender + provider status |
| `POST` | `/api/generate` | run the loop for a brief; persist + return the winner |
| `GET`  | `/api/projects` | list projects |
| `GET`  | `/api/projects/{id}` | a project with its runs + artifacts |
| `GET`  | `/api/artifacts/{id}/file` | download an artifact (code / render / hero) |

`POST /api/generate` body: `{ "brief": "a ceramic mug, studio product render", "quick": true }`
(optional: `candidates`, `rounds`, `target`, `workers`). Returns
`{ project_id, run_id, score, critique, artifacts }`.

## Storage

- SQLite at `LUDWIG_DB` (default `<repo>/ludwig.db`).
- Per-project folders at `LUDWIG_PROJECTS/<id>/` (default `<repo>/projects/<id>/`) holding
  `scene.py` (the program — source of truth), `render.png`, and `hero.png`.

Both are gitignored. Tests point them at a tmp dir.

## Test

```bash
./.venv/bin/pytest tests/test_daemon.py -q
```

The test monkeypatches `ludwig.run`, so it spends **zero** Blender time and zero LLM
tokens — it verifies the wiring (persist + copy + serve), not the loop itself.
The loop is covered by `python3 ludwig.py --selftest`.
