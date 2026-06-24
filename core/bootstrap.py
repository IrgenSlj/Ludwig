"""Register the default engine + sensors. Import for side effects:

    import core.bootstrap   # registers BlenderAdapter + VisionCritic

Kept separate from package import so tests can build registries in isolation.
"""
from __future__ import annotations

from adapters.engines.blender.adapter import BlenderAdapter
from sensors.vision_critic import VisionCritic

from . import registry

registry.register_adapter(BlenderAdapter())
registry.register_sensor(VisionCritic())
