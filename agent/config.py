"""ludwig.toml — the harness runtime config surface (docs/V2_ROADMAP.md §4).

Owns only the NEW v2 harness knobs (search / budget / telemetry). Domain standards and inference
tiers stay in `standards.yaml` (already working — not relitigated). This module is intentionally
**dependency-light**: stdlib `tomllib` + `dataclasses` + `hashlib` only, so importing/using it never
pulls a third-party dep and `cli.py --selftest` stays green on bare Python.

Resolution order (lowest → highest precedence): dataclass defaults → `ludwig.toml` → CLI overrides.
The resolved config's `config_hash()` is stamped into every run manifest (WS7) so a run is reproducible.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

_DEFAULT_PATH = Path("ludwig.toml")


@dataclass
class SearchConfig:
    """Deliberative-search knobs (WS2). `veri_ratio` tunes explore↔refine because our verifier is free."""
    depth: int = 3
    branch: int = 3
    keep_k: int = 1
    veri_ratio: float = 0.5
    seed: int = 0

    def validate(self) -> None:
        if self.depth < 1:
            raise ValueError(f"search.depth must be >= 1, got {self.depth}")
        if self.branch < 1:
            raise ValueError(f"search.branch must be >= 1, got {self.branch}")
        if self.keep_k < 1:
            raise ValueError(f"search.keep_k must be >= 1, got {self.keep_k}")
        if not 0.0 <= self.veri_ratio <= 1.0:
            raise ValueError(f"search.veri_ratio must be in [0, 1], got {self.veri_ratio}")


@dataclass
class BudgetConfig:
    """Hard budget caps (WS1/WS2). On cap-hit the search returns the best branch found so far."""
    max_calls: int = 60
    cost_confirm_usd: float = 5.0

    def validate(self) -> None:
        if self.max_calls < 1:
            raise ValueError(f"budget.max_calls must be >= 1, got {self.max_calls}")
        if self.cost_confirm_usd < 0:
            raise ValueError(f"budget.cost_confirm_usd must be >= 0, got {self.cost_confirm_usd}")


@dataclass
class TelemetryConfig:
    """Trajectory-store knobs (WS7). Local-only by default; no upload path exists in v2."""
    enabled: bool = True
    runs_dir: str = "runs"


@dataclass
class HarnessConfig:
    """The resolved v2 harness config. `config_hash` identifies a run's settings in its manifest."""
    search: SearchConfig = field(default_factory=SearchConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)

    def validate(self) -> "HarnessConfig":
        self.search.validate()
        self.budget.validate()
        return self

    def config_hash(self) -> str:
        """Stable 12-char hash of the fully-resolved config — stamped into every run manifest (WS7).

        Deterministic across processes (sorted-key JSON of the dataclass tree), so the same resolved
        settings always hash identically and a manifest pins exactly what produced a run.
        """
        blob = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_section(section_cls, raw: dict) -> Any:
    """Build a section dataclass from a raw TOML table, dropping keys the dataclass doesn't declare.

    tomllib already yields correctly-typed scalars (int/float/bool/str), so unknown keys are simply
    ignored (forward-compatible with a newer ludwig.toml) rather than raising.
    """
    known = {f.name for f in fields(section_cls)}
    kwargs = {k: v for k, v in raw.items() if k in known}
    return section_cls(**kwargs)


def _coerce_override(current: Any, value: Any) -> Any:
    """Coerce a CLI-supplied override (often a string) to the field's live type. bool before int."""
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(current, int):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return value


def _apply_overrides(cfg: HarnessConfig, overrides: dict[str, Any]) -> HarnessConfig:
    """Apply a flat dict of dotted overrides, e.g. {"search.depth": 5, "budget.max_calls": "30"}."""
    for dotted, value in overrides.items():
        section_name, _, key = dotted.partition(".")
        section = getattr(cfg, section_name, None)
        if section is None or not hasattr(section, key):
            raise KeyError(f"unknown config key: {dotted!r}")
        setattr(section, key, _coerce_override(getattr(section, key), value))
    return cfg


def load_config(path: Optional[Path] = None, *, overrides: Optional[dict[str, Any]] = None) -> HarnessConfig:
    """Resolve `ludwig.toml` (+ optional CLI overrides) into a validated `HarnessConfig`.

    A missing file yields all-defaults (the config surface is optional). `overrides` is a flat dict of
    dotted keys (`"search.depth"`), typically assembled from CLI flags. Raises ValueError on an
    out-of-range value and KeyError on an unknown override key.
    """
    path = Path(path) if path is not None else _DEFAULT_PATH
    data: dict[str, Any] = {}
    if path.exists():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    cfg = HarnessConfig(
        search=_coerce_section(SearchConfig, data.get("search", {})),
        budget=_coerce_section(BudgetConfig, data.get("budget", {})),
        telemetry=_coerce_section(TelemetryConfig, data.get("telemetry", {})),
    )
    if overrides:
        cfg = _apply_overrides(cfg, overrides)
    return cfg.validate()
