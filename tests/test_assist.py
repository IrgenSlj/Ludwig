"""PLAN 5.5: assist drafts and explains; it never touches a verdict."""

import sys
from pathlib import Path

import pytest

from ludwig.assist import drafts
from ludwig.assist.provider import AssistFailed, CommandProvider, from_env
from ludwig.model import Finding, Severity, Status
from ludwig.rules.packs import load_pack

ROOT = Path(__file__).resolve().parent.parent
FAKE = ROOT / "tests" / "assist" / "fake_model.py"
PACK = ROOT / "tests" / "packs" / "demo"

GOOD_RULE = """```yaml
- id: frame-height-max
  kind: require
  applies_to: {type: window_sash}
  require: height_mm <= 3000
  severity: warning
  message: "Sash {mark}: height {height_mm} mm"
```"""
BAD_RULE = '- id: x\n  kind: require\n  require: colour == "red"\n  severity: blocker\n'
MAPPING = (
    "```yaml\nheader_row: 1\ntype: frame\ncolumns: {mark: Pos, width_mm: B, quantity: Stuks}\n```"
)


class Canned:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.answer


def test_draft_rule_is_checked_by_loading_the_pack():
    pack = load_pack(PACK)
    model = Canned(GOOD_RULE)
    draft = drafts.draft_rule("Sashes higher than 3 m cannot be glazed on our line.", pack, model)
    assert draft.problems == [] and draft.text.startswith("- id: frame-height-max")
    assert "limits.sash.max_width_mm" in model.prompts[0]
    bad = drafts.draft_rule("anything", pack, Canned(BAD_RULE))
    assert bad.problems and "unknown name 'colour'" in bad.problems[0]
    assert (PACK / "checks.yaml").read_text().count("- id:") == 3  # nothing was saved


def test_mapping_suggestion_names_only_real_headers():
    draft = drafts.suggest_mapping(["Pos", "B", "H", "Stuks"], Canned(MAPPING))
    assert draft.problems == [] and "mark: Pos" in draft.text
    wrong = drafts.suggest_mapping(["Pos"], Canned(MAPPING))
    assert "column 'B' is not in the headers" in wrong.problems


def test_explanation_leaves_the_finding_alone():
    f = Finding("erp-width", "p", "1", Status.FAIL, Severity.BLOCKER, ["a"], mark="05",
                message="Frame 05: width 4835 vs 4855")  # fmt: skip
    before = f.to_dict()
    assert drafts.explain(f, Canned("The factory will make it 20 mm too wide.")).startswith("The")
    assert f.to_dict() == before


def test_command_provider(tmp_path, monkeypatch):
    answers = tmp_path / "answers.txt"
    answers.write_text("plain words\n=====\nmapping\n=====\nrule")
    provider = CommandProvider(f"{sys.executable} {FAKE} {answers}")
    assert provider.complete("Explain this") == "plain words"
    with pytest.raises(AssistFailed, match="not found"):
        CommandProvider("no-such-model-cli").complete("x")
    with pytest.raises(AssistFailed, match="failed"):
        CommandProvider(f"{sys.executable} -c 'import sys; sys.exit(3)'").complete("x")
    monkeypatch.delenv("LUDWIG_ASSIST_COMMAND", raising=False)
    assert from_env() is None
