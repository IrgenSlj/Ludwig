"""Backends — derived projections of the IR (BRIEF §2.4)."""
from backends.base import Backend
from backends.registry import all, by_name, compile, fabrication, register

# Import backends to trigger registration
import backends.step  # noqa: F401
import backends.ifc  # noqa: F401
import backends.drawing  # noqa: F401
import backends.shopdrawing  # noqa: F401
import backends.section  # noqa: F401
import backends.present  # noqa: F401
# backends.render is intentionally NOT imported: its compile() is an unimplemented P1 stub, so
# auto-registering it would fail every multi-backend compile. P1 re-adds it when compile() is real.

__all__ = ["Backend", "all", "by_name", "compile", "fabrication", "register"]
