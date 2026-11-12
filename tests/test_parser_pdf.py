import sys
from pathlib import Path

import pytest

from ludwig.model import SourceKind
from ludwig.parsers import pdf, schedule

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
SCHEDULE_PDF = FIX / "pdf" / "duplex_joinery_schedule.pdf"
sys.path.insert(0, str(ROOT / "tools"))
import minipdf  # noqa: E402


def summary(elements):
    return sorted((e.mark, e.quantity, e.width_mm, e.height_mm, e.location,
                   tuple(sorted(e.props.items()))) for e in elements)  # fmt: skip


@pytest.fixture(scope="module")
def mapping():
    return pdf.load_mapping(SCHEDULE_PDF.with_suffix(".mapping.yaml"))


def test_vector_schedule_over_two_pages_reads_like_the_csv(mapping):
    elements, warnings = pdf.parse(SCHEDULE_PDF, mapping)
    assert warnings == []
    csv = FIX / "schedule" / "duplex_joinery_schedule.csv"
    expected, _ = schedule.parse(csv, schedule.load_mapping(csv.with_suffix(".mapping.yaml")))
    assert summary(elements) == summary(expected)


def test_values_point_to_page_and_box(mapping):
    elements, _ = pdf.parse(SCHEDULE_PDF, mapping)
    roof = next(e for e in elements if e.mark == "36")
    src = roof.field_sources["width_mm"]
    assert src.kind is SourceKind.PDF and src.page == 2
    x0, top, x1, bottom = src.bbox
    assert x0 < x1 and top < bottom
    assert roof.width_mm == 1172.5


def test_pages_filter(mapping):
    elements, _ = pdf.parse(SCHEDULE_PDF, {**mapping, "pages": [2]})
    assert len(elements) == 5  # page 2 alone: its own header row, rows 8-12
    _, warnings = pdf.parse(SCHEDULE_PDF, {**mapping, "pages": [3]})
    assert [w.message for w in warnings] == ["page 3: not in the file"]


def test_scanned_page_and_loose_text_are_warnings_not_guesses(tmp_path, mapping):
    scan, loose = minipdf.Page(), minipdf.Page()
    scan.line(10, 10, 100, 10)
    loose.text(50, 50, "Merk Aantal")
    path = tmp_path / "mixed.pdf"
    minipdf.write(path, [scan, loose])
    elements, warnings = pdf.parse(path, mapping)
    assert elements == []
    assert [(w.message, w.source.page) for w in warnings] == [
        ("page 1: no vector text, not read", 1), ("page 2: no ruled table", 2)]  # fmt: skip


def test_unreadable_file_and_bad_mapping(tmp_path, mapping):
    junk = tmp_path / "junk.pdf"
    junk.write_text("not a pdf")
    elements, warnings = pdf.parse(junk, mapping)
    assert elements == [] and "cannot read PDF file" in warnings[0].message
    bad = tmp_path / "m.yaml"
    bad.write_text("type: frame\npages: [0]\n")
    with pytest.raises(ValueError, match="pages"):
        pdf.load_mapping(bad)
