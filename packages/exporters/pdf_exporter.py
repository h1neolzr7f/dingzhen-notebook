"""Unicode-safe study-paper PDF export with a fail-closed minimal fallback."""

from __future__ import annotations

import html as html_lib
import re
from pathlib import Path
from typing import Iterable


def _text_lines(document: str) -> list[str]:
    value = re.sub(r"<head\b[^>]*>.*?</head>", "", document, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", "", value, flags=re.I | re.S)
    value = re.sub(r"<script\b[^>]*>.*?</script>", "", value, flags=re.I | re.S)
    value = re.sub(r"<\s*(br|/p|/div|/h[1-6]|/li|/tr|/article|/table|/body)\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html_lib.unescape(value).replace("\r", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    return [line for line in lines if line]


def _fallback_pdf(lines: Iterable[str]) -> bytes:
    # Keep each page well within the default media box.  Replacing characters
    # outside WinAnsi is preferable to writing invalid UTF-8 into a PDF string.
    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        safe = line.encode("latin-1", "replace").decode("latin-1")
        # Split very long stems so they do not run outside the page.
        chunks = [safe[index : index + 100] for index in range(0, max(1, len(safe)), 100)]
        for chunk in chunks:
            if len(current) >= 48:
                pages.append(current)
                current = []
            current.append(chunk)
    if current or not pages:
        pages.append(current)

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_refs = " ".join(f"{4 + index * 2} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {len(pages)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, page_lines in enumerate(pages):
        page_object = 4 + index * 2
        stream_object = page_object + 1
        stream_lines = ["BT", "/F1 10 Tf", "40 800 Td"]
        for line_index, line in enumerate(page_lines):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if line_index:
                stream_lines.append("0 -15 Td")
            stream_lines.append(f"({escaped}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_object} 0 R >>".encode(
                "ascii"
            )
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(output)


def _reportlab_pdf(lines: list[str], destination: Path) -> bool:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except Exception:
        return False
    font = "FenbiUnicode"
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ):
        if candidate.exists():
            try:
                pdfmetrics.registerFont(TTFont(font, str(candidate)))
                break
            except Exception:
                pass
    else:
        # ReportLab ships the standard Simplified-Chinese CID font mapping,
        # which preserves Unicode instead of replacing glyphs with '?'.
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font = "STSong-Light"

    body = ParagraphStyle(
        "FenbiBody",
        fontName=font,
        fontSize=10.5,
        leading=16,
        textColor="#1f2937",
        wordWrap="CJK",
        spaceAfter=4,
    )
    title = ParagraphStyle(
        "FenbiTitle",
        parent=body,
        fontSize=18,
        leading=24,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    story = []
    for index, line in enumerate(lines):
        style = title if index == 0 else body
        story.append(Paragraph(html_lib.escape(line), style))
        if index == 0:
            story.append(Spacer(1, 3 * mm))

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor("#6b7280")
        canvas.drawCentredString(A4[0] / 2, 9 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=lines[0] if lines else "粉笔学习资料",
        author="fenbi-study-pipeline",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return True


def html_to_pdf(document: str, destination: str | Path) -> Path:
    """Write ``document`` to a valid PDF and return its path."""

    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = _text_lines(document)
    if not _reportlab_pdf(lines, output):
        if any(ord(character) > 255 for line in lines for character in line):
            output.unlink(missing_ok=True)
            raise RuntimeError("A Unicode-capable PDF renderer (ReportLab) is required for Chinese output")
        output.write_bytes(_fallback_pdf(lines))
    return output


def export_html_to_pdf(document: str, destination: str | Path) -> Path:
    return html_to_pdf(document, destination)


export_pdf = html_to_pdf
render_pdf = html_to_pdf
write_pdf = html_to_pdf


def export_paper_bundle_pdf(
    paper_or_repository: object,
    questions_or_paper_id: object,
    destination: str | Path,
    **kwargs: object,
) -> object:
    """Lazy wrapper avoiding an import cycle with ``paper_builder``."""

    from packages.paper_builder import build_paper_bundle

    return build_paper_bundle(paper_or_repository, questions_or_paper_id, destination, formats=("pdf",), **kwargs)


__all__ = [
    "export_html_to_pdf",
    "export_paper_bundle_pdf",
    "export_pdf",
    "html_to_pdf",
    "render_pdf",
    "write_pdf",
]
