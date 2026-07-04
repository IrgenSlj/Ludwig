"""The skeleton imports clean WITHOUT the heavy kernels (cadquery/ifcopenshell/bpy) installed.

This guards the lazy-import discipline (BRIEF §4 / CLAUDE.md): heavy deps must never import at
package load, so --selftest and CI stay green before the kernel lands.
"""
import importlib

import pytest

PURE_MODULES = [
    "ir", "ir.elements",
    "geometry", "geometry.service",
    "toolkit", "toolkit.elements", "toolkit.standards",
    "eval", "eval.briefs", "eval.harness", "eval.reference", "eval.llm",
    "backends", "backends.base", "backends.step", "backends.drawing", "backends.ifc",
    "critic", "critic.base", "critic.panel", "critic.dimensional", "critic.geometric", "critic.semantic", "critic.manufacturing",
    "agent", "agent.inference", "agent.loop",
    "store", "store.repairs",
    "cli",
]


@pytest.mark.parametrize("mod", PURE_MODULES)
def test_imports_clean(mod):
    importlib.import_module(mod)


def test_selftest_passes():
    import cli
    assert cli.selftest() == 0
