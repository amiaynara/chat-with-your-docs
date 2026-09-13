import pytest

from app.ingestion.chunking import chunk_sections
from app.ingestion.parsing import DocumentParseError, parse_document
from app.ingestion.spans import TextSpan
from app.models import DocumentFormat
from tests.pdf_fixtures import pdf_with_blank_page, pdf_with_text


def test_parse_document_pdf_extracts_text_per_page():
    data = pdf_with_text("First page.", "Second page.")

    sections = parse_document(data, DocumentFormat.PDF)

    assert [s.text for s in sections] == ["First page.", "Second page."]
    assert [s.location_ref for s in sections] == ["page 1", "page 2"]


def test_parse_document_pdf_raises_when_no_extractable_text():
    data = pdf_with_blank_page()

    with pytest.raises(DocumentParseError, match="no extractable text"):
        parse_document(data, DocumentFormat.PDF)


def test_parse_document_pdf_raises_on_corrupt_bytes():
    with pytest.raises(DocumentParseError, match="Could not read PDF"):
        parse_document(b"not actually a pdf", DocumentFormat.PDF)


def test_parse_document_txt_raises_on_invalid_utf8():
    with pytest.raises(DocumentParseError, match="Could not decode file as UTF-8"):
        parse_document(b"\xff\xfe not valid utf-8", DocumentFormat.TXT)


def test_parse_document_txt_raises_when_whitespace_only():
    with pytest.raises(DocumentParseError, match="Document is empty"):
        parse_document(b"   \n\t  ", DocumentFormat.TXT)


def test_parse_document_txt_returns_single_section():
    sections = parse_document(b"Hello, world.", DocumentFormat.TXT)

    assert sections == [TextSpan(text="Hello, world.", location_ref="document")]


def test_chunk_sections_keeps_short_text_as_one_chunk():
    sections = [TextSpan(text="short text", location_ref="page 1")]

    chunks = chunk_sections(sections, chunk_size=1000, overlap_ratio=0.1)

    assert chunks == [TextSpan(text="short text", location_ref="page 1")]


def test_chunk_sections_splits_long_text_with_overlap():
    text = "0123456789" * 5  # 50 chars
    sections = [TextSpan(text=text, location_ref="page 1")]

    chunks = chunk_sections(sections, chunk_size=20, overlap_ratio=0.5)

    assert len(chunks) > 1
    assert all(chunk.location_ref == "page 1" for chunk in chunks)
    assert "".join(chunks[0].text[:10]) == text[:10]
    # overlap: each chunk after the first repeats the tail of the previous one
    assert chunks[1].text[:10] == chunks[0].text[10:20]
    # every chunk fits within the configured chunk_size
    assert all(len(chunk.text) <= 20 for chunk in chunks)
    # the full text is covered by the final chunk's end
    assert chunks[-1].text[-1] == text[-1]
