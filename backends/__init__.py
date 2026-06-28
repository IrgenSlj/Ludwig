"""Backends — derived projections of the IR (BRIEF §2.4)."""
from backends.base import Backend
from backends.registry import all, by_name, compile, fabrication, register

# Import backends to trigger registration
import backends.step  # noqa: F401
import backends.ifc  # noqa: F401
import backends.drawing  # noqa: F401
import backends.render  # noqa: F401

__all__ = ["Backend", "all", "by_name", "compile", "fabrication", "register"]
