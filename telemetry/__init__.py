"""telemetry — run manifests + the trajectory dataset (WS7, docs/V2_ROADMAP.md §3).

Every run's compounding asset: a manifest (config hash, models, seed, git commit) + an append-only
trajectory JSONL + content-addressed media, under `runs/<run_id>/`. This is the store that lets a run
`replay` deterministically and lets `dataset export` package training-ready trajectories offline.

M1 ships the thin stdlib store below (`RunStore`). The typed pydantic event schema
(`telemetry/schema.py`) and `replay`/`export` land in WS7 and import pydantic **lazily**, so this
package stays importable — and `--selftest` stays green — without pydantic installed.
"""
from telemetry.store import RunStore

__all__ = ["RunStore"]
