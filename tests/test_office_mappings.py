"""PLAN 3.5: office conventions live in mapping files beside the input, never in code."""

import json
import shutil
from pathlib import Path

import ezdxf
import pytest

from ludwig.cli import main
from ludwig.parsers import dxf, ifc

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "mappings" / "examples"
PACK = ROOT / "packs" / "joinery-nl"


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("dxf_*.yaml")))
def test_example_dxf_mappings_load(name):
    assert dxf.load_mapping(EXAMPLES / name)["blocks"]


def test_example_ifc_mapping_loads():
    assert ifc.load_mapping(EXAMPLES / "ifc_reference_mark.yaml")["mark"]


def office_drawing(path: Path) -> None:
    doc = ezdxf.new(setup=False)
    doc.header["$INSUNITS"] = 4
    block = doc.blocks.new("K_STD")
    for tag in ("KOZ_NR", "B_MM", "H_MM", "DRAAI"):
        block.add_attdef(tag, (0, 0))
    for layer, direction in (("31-KOZIJN", "L"), ("31-KOZIJN", "R"), ("HULPLIJNEN", "L")):
        ref = doc.modelspace().add_blockref("K_STD", (0, 0), dxfattribs={"layer": layer})
        ref.add_auto_attribs({"KOZ_NR": "k12", "B_MM": "92,5", "H_MM": "231,5", "DRAAI": direction})
    doc.saveas(path)


def elements(tmp_path, *files):
    out = tmp_path / "out"
    main(["check", "--architect", *map(str, files), "--pack", str(PACK), "--out", str(out)])
    return json.loads((out / "report.json").read_text())["summary"]["elements_total"]


def test_office_dxf_needs_its_mapping_beside_it(tmp_path):
    drawing = tmp_path / "plattegrond.dxf"
    office_drawing(drawing)
    assert dxf.parse(drawing)[0] == []  # default mapping: unknown block name, nothing read
    assert elements(tmp_path, drawing) == 0
    shutil.copy(EXAMPLES / "dxf_office_tags.yaml", tmp_path / "plattegrond.mapping.yaml")
    assert elements(tmp_path, drawing) == 2  # left and right; the HULPLIJNEN copy is skipped
    found, _ = dxf.parse(drawing, dxf.load_mapping(tmp_path / "plattegrond.mapping.yaml"))
    assert sorted((e.mark, e.width_mm, e.height_mm, e.props["opening_direction"])
                  for e in found) == [("K12", 925.0, 2315.0, "left"),
                                      ("K12", 925.0, 2315.0, "right")]  # fmt: skip


def test_office_ifc_mapping_beside_the_model_is_used(tmp_path):
    model = tmp_path / "duplex.ifc"
    shutil.copy(ROOT / "fixtures" / "ifc" / "duplex_architectural_ifc2x3.ifc", model)
    default = elements(tmp_path, model)
    (tmp_path / "duplex.mapping.yaml").write_text(
        "classes: {IfcDoor: frame}\nmark: ['pset:PSet_Revit_Type_Identity Data.Type Mark']\n"
        "width: ['attr:OverallWidth']\nheight: ['attr:OverallHeight']\n"
    )
    assert default == 12 and elements(tmp_path, model) == 4  # door positions only
