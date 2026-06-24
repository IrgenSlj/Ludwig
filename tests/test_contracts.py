"""M4 contract-layer tests — all offline (no Blender, no LLM tokens).

Proves the architecture is real and pluggable: registry resolution by capability,
the prompt stack, skill/standards loaders, the vision critic behind the Sensor
contract (with a canned critique), and the contract-driven orchestrator with fakes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import loaders, prompt_stack, registry  # noqa: E402
from core.contracts import Sensor, ToolAdapter  # noqa: E402
from core.models import Brief, Caps, Critique, RunResult  # noqa: E402


# --- fakes -----------------------------------------------------------------
class FakeAdapter:
    name = "fake"
    language = "toy"

    def capabilities(self):
        return Caps(mesh=True, outputs=("png",), tags=frozenset({"fake"}))

    def toolkit_reference(self):
        return "use fake_box()"

    def run(self, program, project_dir):
        return RunResult(code=program, ok=True, renders=["/tmp/fake.png"])

    def preview(self, result):
        return None


class FakeSensor:
    name = "fake-scorer"
    applies_to = {"fake"}

    def evaluate(self, result, brief):
        return Critique(score=6.0, axis_scores={"X": 6.0})


# --- tests -----------------------------------------------------------------
def test_runtime_conformance():
    from adapters.engines.blender.adapter import BlenderAdapter
    from sensors.vision_critic import VisionCritic

    assert isinstance(BlenderAdapter(), ToolAdapter)
    assert isinstance(VisionCritic(), Sensor)
    assert isinstance(FakeAdapter(), ToolAdapter)
    assert isinstance(FakeSensor(), Sensor)


def test_registry_resolves_by_capability():
    registry.register_adapter(FakeAdapter())
    registry.register_sensor(FakeSensor())
    assert "fake" in registry.adapters()
    caps = registry.get_adapter("fake").capabilities()
    names = {s.name for s in registry.sensors_for(caps)}
    assert "fake-scorer" in names  # tag "fake" matches
    # a sensor for unrelated tags is not selected
    assert all(s.applies_to & set(caps.tags) for s in registry.sensors_for(caps))


def test_bootstrap_registers_defaults():
    import core.bootstrap  # noqa: F401  (side-effect registration)
    from adapters.engines.blender.adapter import BlenderAdapter

    assert "blender" in registry.adapters()
    caps = BlenderAdapter().capabilities()
    assert {"image", "render"} <= set(caps.tags)
    assert "vision" in {s.name for s in registry.sensors_for(caps)}


def test_prompt_stack_composes_layers():
    out = prompt_stack.build_prompt(
        Brief(text="a mug", discovery={"units": "cm", "tolerance": "n/a"}),
        identity="You are Ludwig.",
        standards={"units": "model in cm"},
        skill_body="fill the frame",
        toolkit_reference="L_pbr(...)",
        project_meta={"target_output": "render"},
    )
    for label in ("IDENTITY", "STANDARDS", "SKILL", "PROJECT", "TOOLKIT", "BRIEF"):
        assert f"=== {label} ===" in out
    assert "a mug" in out and "units: cm" in out
    assert "tolerance" not in out  # n/a skipped from the locked block


def test_loaders_read_files():
    meta, body = loaders.parse_frontmatter("---\nname: x\nengine: blender\n---\nhello")
    assert meta["engine"] == "blender" and body.strip() == "hello"

    assert "units" in loaders.available_standards()
    assert "model" in loaders.load_standards(["units"])["units"].lower()

    skill = loaders.load_skill("product-render")
    assert skill and skill["meta"]["engine"] == "blender"
    assert "product-render" in loaders.available_skills()


def test_vision_critic_parses_canned_critique(monkeypatch):
    import ludwig
    from sensors.vision_critic import VisionCritic

    canned = (
        "FRAMING: 7\nLIGHTING: 6\nMATERIALS: 5\nBRIEF: 8\nBELIEVABILITY: 6\n"
        "KEEP: nice silhouette\nFIXES:\n- raise the key light\n- add a contact shadow\n"
    )
    monkeypatch.setattr(ludwig, "critique", lambda brief, png: canned)
    c = VisionCritic().evaluate(
        RunResult(code="x", ok=True, renders=["/x.png"]), Brief(text="a mug"))
    assert c.score > 0
    assert c.axis_scores.get("FRAMING") == 7.0
    assert c.repair_hints == ["raise the key light", "add a contact shadow"]


def test_orchestrator_runs_via_contracts(monkeypatch):
    from core import orchestrator

    registry.register_adapter(FakeAdapter())
    registry.register_sensor(FakeSensor())
    out = orchestrator.run_via_contracts(
        Brief(text="a mug"), "/tmp/ludwig-test-proj",
        engine="fake", generate=lambda text: "# code",
    )
    assert out["result"].ok
    assert out["score"] == 6.0
    assert "fake-scorer" in out["sensors"]
