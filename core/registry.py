"""Registries: resolve engines + sensors without the orchestrator knowing them.

The orchestrator asks for an adapter by name and for the sensors whose ``applies_to``
intersects the active engine's capability tags, then aggregates their verdicts.
"""
from __future__ import annotations

from .contracts import Sensor, ToolAdapter
from .models import Caps

_ADAPTERS: dict[str, ToolAdapter] = {}
_SENSORS: dict[str, Sensor] = {}


def register_adapter(adapter: ToolAdapter) -> ToolAdapter:
    _ADAPTERS[adapter.name] = adapter
    return adapter


def register_sensor(sensor: Sensor) -> Sensor:
    _SENSORS[sensor.name] = sensor
    return sensor


def get_adapter(name: str) -> ToolAdapter:
    if name not in _ADAPTERS:
        raise KeyError(f"no engine adapter registered as {name!r} "
                       f"(have: {sorted(_ADAPTERS)})")
    return _ADAPTERS[name]


def adapters() -> list[str]:
    return sorted(_ADAPTERS)


def sensors_for(caps: Caps) -> list[Sensor]:
    """Sensors whose applies_to intersects the engine's capability tags."""
    return [s for s in _SENSORS.values() if set(s.applies_to) & set(caps.tags)]


def all_sensors() -> list[Sensor]:
    return list(_SENSORS.values())
