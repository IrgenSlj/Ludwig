from pathlib import Path

import pytest

from ludwig.adapters import erp_table
from ludwig.match import pairs
from ludwig.model import Status
from ludwig.parsers import ifc, schedule
from ludwig.rules import engine, fixtures
from ludwig.rules.packs import load_pack

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"


@pytest.fixture(scope="module")
def pack():
    return load_pack(ROOT / "packs" / "joinery-nl")


def test_every_rule_passes_and_fails_on_its_fixtures(pack):
    assert fixtures.check(pack) == []


def test_clean_duplex_project_has_no_findings(pack):
    elements, _ = ifc.parse(FIX / "ifc" / "duplex_architectural_ifc2x3.ifc")
    sched = FIX / "schedule" / "duplex_joinery_schedule.csv"
    elements += schedule.parse(sched, schedule.load_mapping(sched.with_suffix(".mapping.yaml")))[0]
    export = FIX / "erp" / "duplex_erp_export.csv"
    elements += erp_table.parse(export, erp_table.load_mapping(
        export.with_suffix(".mapping.yaml")))[0]  # fmt: skip
    result = engine.run(elements, pack, pairs(elements, pack.match_tolerance_mm))
    bad = [f.message for f in result.findings if f.status in (Status.FAIL, Status.NOT_CHECKED)]
    assert bad == []
    door33 = [f for f in result.findings if f.rule_id == "erp-fire-rating" and f.mark == "33"]
    assert [f.status for f in door33] == [Status.PASS]
