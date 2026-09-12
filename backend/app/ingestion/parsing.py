import io

from pypdf import PdfReader

from app.ingestion.spans import TextSpan
from app.models import DocumentFormat


class DocumentParseError(Exception):
    """Raised when a document's bytes can't be parsed as its declared format."""


def parse_document(data: bytes, document_format: DocumentFormat) -> list[TextSpan]:
    """Extract text sections from raw file bytes, tagged with a human-readable location.

    One section per PDF page; a single section for txt/md.
    """
    if document_format == DocumentFormat.PDF:
        return _parse_pdf(data)
    return _parse_text(data)


def _parse_pdf(data: bytes) -> list[TextSpan]:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pypdf raises several distinct exception types
        raise DocumentParseError(f"Could not read PDF: {exc}") from exc

    sections = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append(TextSpan(text=text, location_ref=f"page {page_number}"))

    if not sections:
        raise DocumentParseError("PDF contains no extractable text")
    return sections


def _parse_text(data: bytes) -> list[TextSpan]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentParseError(f"Could not decode file as UTF-8 text: {exc}") from exc

    text = text.strip()
    if not text:
        raise DocumentParseError("Document is empty")
    return [TextSpan(text=text, location_ref="document")]
