"""A minimal vector PDF writer for invented fixtures: lines and Helvetica text, nothing else."""

from __future__ import annotations

from pathlib import Path


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Page:
    """One page; coordinates in points from the bottom-left corner, as in PDF."""

    def __init__(self, width: float = 842, height: float = 595):
        self.width, self.height = width, height
        self.ops: list[str] = []

    def line(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """A 0.5 pt stroked line."""
        self.ops.append(f"0.5 w {x0:.2f} {y0:.2f} m {x1:.2f} {y1:.2f} l S")

    def text(self, x: float, y: float, text: str, size: float = 8) -> None:
        """Text with its baseline starting at (x, y)."""
        self.ops.append(f"BT /F1 {size:g} Tf {x:.2f} {y:.2f} Td ({_escape(text)}) Tj ET")


def write(path: str | Path, pages: list[Page]) -> None:
    """Write the pages as a PDF 1.4 file with fixed bytes for fixed input."""
    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                   b"/Encoding /WinAnsiEncoding >>")  # fmt: skip
    for page, pid in zip(pages, page_ids, strict=True):
        stream = "\n".join(page.ops).encode("cp1252")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page.width:g} {page.height:g}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {pid + 1} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref)  # fmt: skip
    Path(path).write_bytes(bytes(out))
