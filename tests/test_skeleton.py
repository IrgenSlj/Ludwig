"""The skeleton imports clean WITHOUT the heavy kernels (cadquery/ifcopenshell/bpy) installed.

This guards the lazy-import discipline (BRIEF §4 / CLAUDE.md): heavy deps must never import at
package load, so --selftest and CI stay green before the kernel lands.
"""
import importlib

import pytest

PURE_MODULES = [
    "ir", "ir.elements",
    "geometry", "geometry.service",
    "toolkit", "toolkit.elements",
    "backends", "backends.base", "backends.step", "backends.drawing", "backends.render",
    "critic", "critic.base", "critic.dimensional", "critic.geometric", "critic.semantic",
    "agent", "agent.inference", "agent.loop",
    "store", "store.db",
    "cli",
]


@pytest.mark.parametrize("mod", PURE_MODULES)
def test_imports_clean(mod):
    importlib.import_module(mod)


def test_render_toolkit_not_imported_at_load():
    # backends/render_toolkit.py imports bpy at module load (mesh-era code); it must only be
    # pulled in lazily by backends.render at P1, never by importing the backends package.
    import sys
    importlib.import_module("backends")
    assert "backends.render_toolkit" not in sys.modules


def test_selftest_passes():
    import cli
    assert cli.selftest() == 0
