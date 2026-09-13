"""Builds minimal, real PDF byte strings for parser tests.

pypdf has no convenient text-writing API, so a valid PDF with a real,
extractable text-drawing content stream is built by hand here rather than
pulling in a whole PDF-generation dependency just for test fixtures.
"""

import io

from pypdf import PdfWriter


def pdf_with_text(*page_texts: str) -> bytes:
    """A real, valid PDF with one page per string in `page_texts`."""
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]

    page_count = len(page_texts)
    kids = " ".join(f"{3 + i} 0 R" for i in range(page_count))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())

    font_obj_num = 3 + page_count
    for i in range(page_count):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
                f"/MediaBox [0 0 200 200] /Contents {font_obj_num + 1 + i} 0 R >>"
            ).encode()
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for text in page_texts:
        escaped = text.replace("(", r"\(").replace(")", r"\)")
        content = f"BT /F1 24 Tf 10 100 Td ({escaped}) Tj ET".encode()
        length_header = b"<< /Length " + str(len(content)).encode() + b" >>\n"
        objects.append(length_header + b"stream\n" + content + b"\nendstream")

    return _assemble_pdf(objects)


def pdf_with_blank_page() -> bytes:
    """A real, valid PDF whose one page has no extractable text."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _assemble_pdf(objects: list[bytes]) -> bytes:
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(buf.tell())
        buf.write(str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n")

    xref_offset = buf.tell()
    buf.write(b"xref\n0 " + str(len(objects) + 1).encode() + b"\n")
    buf.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buf.write(f"{offset:010d} 00000 n \n".encode())
    buf.write(
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF"
    )
    return buf.getvalue()
