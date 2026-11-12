from pathlib import Path

import ezdxf
import pytest

from ludwig.model import SourceKind
from ludwig.parsers import dxf, ifc

FIX = Path(__file__).resolve().parent.parent / "fixtures"
PLAN = FIX / "dxf" / "duplex_joinery_plan.dxf"


def summary(elements):
    return sorted((e.mark, e.quantity, e.width_mm, e.height_mm, e.location,
                   tuple(sorted(e.props.items()))) for e in elements)  # fmt: skip


def test_invented_plan_describes_the_same_positions_as_the_model():
    elements, warnings = dxf.parse(PLAN)
    assert warnings == []
    model, _ = ifc.parse(FIX / "ifc" / "duplex_architectural_ifc2x3.ifc")
    assert summary(elements) == summary(model)
    door = next(e for e in elements if e.mark == "33")
    assert door.sources[0].kind is SourceKind.DXF
    assert door.sources[0].layer == "KOZIJNEN" and door.sources[0].dxf_handle
    assert len(door.sources) == 2


def test_door_width_comes_from_block_extents_when_no_attribute():
    doc = ezdxf.readfile(PLAN)
    ref = next(i for i in doc.modelspace().query("INSERT") if i.dxf.name == "DEUR-33-R")
    assert {a.dxf.tag: a.dxf.text for a in ref.attribs}["BREEDTE"] == ""
    door = next(e for e in dxf.parse(PLAN)[0] if e.mark == "33")
    assert door.width_mm == 1250.0


def test_extents_follow_drawing_units_and_scale(tmp_path):
    mapping = dxf.load_mapping()
    mapping["blocks"] = {"*door*": "frame"}
    elements, _ = dxf.parse(FIX / "dxf" / "ezdxf_wipeout_door.dxf", mapping)
    assert [e.width_mm for e in elements] == [26543.0, 26543.0]  # 1045 inch, $INSUNITS 1
    doc = ezdxf.new(setup=False)
    doc.header["$INSUNITS"] = 5  # cm
    block = doc.blocks.new("KOZ-1")
    block.add_line((0, 0), (90, 0))
    doc.modelspace().add_blockref("KOZ-1", (0, 0), dxfattribs={"xscale": 2})
    path = tmp_path / "cm.dxf"
    doc.saveas(path)
    [el] = dxf.parse(path)[0]
    assert el.width_mm == 1800.0 and el.height_mm is None and el.mark is None


def test_layer_filter_and_unknown_blocks_are_skipped(tmp_path):
    doc = ezdxf.new(setup=False)
    doc.header["$INSUNITS"] = 4
    for name in ("KOZ-A", "CHAIR"):
        doc.blocks.new(name).add_line((0, 0), (500, 0))
    msp = doc.modelspace()
    msp.add_blockref("KOZ-A", (0, 0), dxfattribs={"layer": "kozijnen"})
    msp.add_blockref("KOZ-A", (0, 0), dxfattribs={"layer": "HULP"})
    msp.add_blockref("CHAIR", (0, 0), dxfattribs={"layer": "kozijnen"})
    path = tmp_path / "layers.dxf"
    doc.saveas(path)
    mapping = dxf.load_mapping()
    mapping["layers"] = ["KOZIJNEN"]
    [el] = dxf.parse(path, mapping)[0]
    assert el.quantity == 1 and el.sources[0].layer == "kozijnen"


def test_bad_values_and_files_give_warnings(tmp_path):
    doc = ezdxf.new(setup=False)
    doc.header["$INSUNITS"] = 4
    block = doc.blocks.new("KOZ-X")
    block.add_attdef("BREEDTE", (0, 0))
    block.add_attdef("MERK", (0, 0))
    doc.modelspace().add_blockref("KOZ-X", (0, 0)).add_auto_attribs(
        {"BREEDTE": "breed", "MERK": " k 7 "})  # fmt: skip
    path = tmp_path / "bad.dxf"
    doc.saveas(path)
    [el], warnings = dxf.parse(path)
    assert el.mark == "K7" and el.width_mm is None
    assert [w.message for w in warnings] == ["BREEDTE: not a number 'breed'"]
    junk = tmp_path / "junk.dxf"
    junk.write_text("garbage")
    assert dxf.parse(junk)[0] == []
    assert "cannot read DXF file" in dxf.parse(junk)[1][0].message


def test_mapping_is_checked(tmp_path):
    bad = tmp_path / "m.yaml"
    bad.write_text("blocks: {'K*': frame}\nextents: {width_mm: z}\n")
    with pytest.raises(ValueError, match="extents"):
        dxf.load_mapping(bad)
