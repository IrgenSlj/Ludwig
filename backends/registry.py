"""Backend registry — adding a backend must not modify the loop (BRIEF §0 / [H4])."""
from __future__ import annotations

from pathlib import Path

_REGISTRY: dict[str, object] = {}

def register(backend) -> None:
    _REGISTRY[backend.name] = backend

def all() -> list:
    return list(_REGISTRY.values())

def by_name(name: str):
    return _REGISTRY.get(name)

def fabrication() -> list:
    return [b for b in _REGISTRY.values() if getattr(b, "fabrication", False)]

def compile(ir, out_dir: Path) -> dict[str, Path]:
    """Compile IR through all backends. Returns {name: path}."""
    results = {}
    for b in all():
        try:
            results[b.name] = b.compile(ir, out_dir)
        except Exception as e:
            results[f"{b.name}_error"] = f"{type(e).__name__}: {e}"
    return results
