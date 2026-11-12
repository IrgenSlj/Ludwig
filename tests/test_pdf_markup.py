from pathlib import Path

from pypdf import PdfReader

from ludwig.cli import main
from ludwig.parsers import pdf

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
SOURCE = FIX / "pdf" / "duplex_joinery_schedule.pdf"


def test_findings_are_marked_on_a_copy_of_the_source_pdf(tmp_path):
    before = SOURCE.read_bytes()
    out = tmp_path / "out"
    main(["check", "--architect", str(FIX / "dxf" / "duplex_joinery_plan.dxf"), str(SOURCE),
          "--erp", str(FIX / "erp" / "duplex_erp_export_seeded.csv"),
          "--pack", str(ROOT / "packs" / "joinery-nl"), "--out", str(out)])  # fmt: skip
    assert SOURCE.read_bytes() == before
    marked = PdfReader(out / "duplex_joinery_schedule.marked.pdf")
    notes = [a.get_object() for page in marked.pages for a in page.get("/Annots", [])]
    texts = sorted(str(n["/Contents"]) for n in notes)
    assert any(t.startswith("Frame 01: glazing in drawings HR++, production Triple") for t in texts)
    assert any(t.startswith("Frame 33: fire rating") for t in texts)
    glazing = next(n for n in notes if str(n["/Contents"]).startswith("Frame 01: glazing"))
    assert glazing["/Subtype"] == "/Square"
    assert [round(float(c), 2) for c in glazing["/C"]] == [1.0, 0.6, 0.0]  # warning: orange
    elements, _ = pdf.parse(SOURCE, pdf.load_mapping(SOURCE.with_suffix(".mapping.yaml")))
    cell = next(e for e in elements if e.mark == "01").field_sources["props.glazing_type"]
    height = float(marked.pages[cell.page - 1].mediabox.height)
    x0, y0, x1, y1 = (float(v) for v in glazing["/Rect"])
    left, top, right, bottom = cell.bbox
    assert x0 < left < right < x1 and y0 < height - bottom < height - top < y1

def test_no_pdf_evidence_writes_no_markup(tmp_path):
    out = tmp_path / "out"
    main(["check", "--architect", str(FIX / "ifc" / "duplex_architectural_ifc2x3.ifc"),
          "--erp", str(FIX / "erp" / "duplex_erp_export_seeded.csv"),
          "--pack", str(ROOT / "packs" / "joinery-nl"), "--out", str(out)])  # fmt: skip
    assert list(out.glob("*.marked.pdf")) == []
