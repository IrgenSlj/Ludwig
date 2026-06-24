"""M2 glb export test — real Blender, zero LLM tokens.

Exports ``ludwig.SELFTEST_SCENE`` (a known-good scene) to a .glb and asserts it's a
valid glTF-binary file. Skipped when Blender isn't installed, mirroring --selftest.

Run: ./.venv/bin/pytest tests/test_glb.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ludwig  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (ludwig.BLENDER and os.path.exists(ludwig.BLENDER)),
    reason="Blender not installed",
)


def test_export_glb(tmp_path):
    from daemon import glb

    out = tmp_path / "scene.glb"
    ok, log = glb.export_glb(ludwig.SELFTEST_SCENE, out, timeout=180)
    assert ok, f"glb export failed:\n{log[-800:]}"
    assert out.exists() and out.stat().st_size > 0
    # GLB magic header is the ASCII bytes 'glTF'
    assert out.read_bytes()[:4] == b"glTF"


def test_maybe_export_disabled(monkeypatch, tmp_path):
    from daemon import glb

    monkeypatch.setenv("LUDWIG_DISABLE_GLB", "1")
    assert glb.maybe_export(ludwig.SELFTEST_SCENE, tmp_path / "x.glb") is None
