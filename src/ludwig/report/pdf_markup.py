"""PDF markup: copies of the source PDFs with a box and note at each finding's evidence.

The source PDFs are never changed. Boxes come from evidence (page and box in points from
the page's top-left corner, as the PDF parser records them).
"""

from __future__ import annotations

from pathlib import Path

from ludwig.model import Finding, Severity, SourceKind, Status
from ludwig.report import report_order
from ludwig.rules.engine import RunResult

_COLOUR = {Severity.BLOCKER: "ff0000", Severity.WARNING: "ff9900", Severity.INFO: "3366ff"}
_NOT_CHECKED = "808080"
_PAD = 2.0  # points around the words, so the box does not cover them


def marked_files(result: RunResult) -> dict[str, list[tuple[Finding, int, tuple]]]:
    """Per source PDF: the (finding, page, box) marks to draw; fail and not_checked only."""
    marks: dict[str, list[tuple[Finding, int, tuple]]] = {}
    for f in report_order(result.findings):
        if f.status not in (Status.FAIL, Status.NOT_CHECKED):
            continue
        for src in f.evidence:
            if src.kind is not SourceKind.PDF or src.page is None or src.bbox is None:
                continue
            mark = (f, src.page, src.bbox)
            if mark not in marks.setdefault(src.file, []):
                marks[src.file].append(mark)
    return marks


def write(out_dir: str | Path, result: RunResult) -> list[Path]:
    """Write `<name>.marked.pdf` into out_dir for every source PDF with findings."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Rectangle
    from pypdf.generic import NameObject, TextStringObject

    out_dir = Path(out_dir)
    written = []
    for file, marks in sorted(marked_files(result).items()):
        writer = PdfWriter(clone_from=PdfReader(file))
        for f, page_no, (x0, top, x1, bottom) in marks:
            if page_no > len(writer.pages):
                continue
            height = float(writer.pages[page_no - 1].mediabox.height)
            rect = (x0 - _PAD, height - bottom - _PAD, x1 + _PAD, height - top + _PAD)
            colour = _NOT_CHECKED if f.status is Status.NOT_CHECKED else _COLOUR[f.severity]
            note = Rectangle(rect=rect)
            note[NameObject("/C")] = _rgb(colour)
            text = f.message or f.rule_id
            if f.reason:
                text += f" ({f.reason})"
            note[NameObject("/Contents")] = TextStringObject(text)
            note[NameObject("/T")] = TextStringObject(f"ludwig {f.rule_id}")
            writer.add_annotation(page_number=page_no - 1, annotation=note)
        target = out_dir / f"{Path(file).stem}.marked.pdf"
        with target.open("wb") as fh:
            writer.write(fh)
        written.append(target)
    return written


def _rgb(hex_colour: str):  # noqa: ANN202 - a pypdf ArrayObject
    from pypdf.generic import ArrayObject, FloatObject

    return ArrayObject(FloatObject(int(hex_colour[i : i + 2], 16) / 255) for i in (0, 2, 4))
