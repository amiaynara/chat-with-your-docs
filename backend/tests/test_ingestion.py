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


def test_chunk_sections_packs_paragraphs_without_splitting_one_mid_way():
    paragraphs = ["First paragraph here.", "Second paragraph here.", "Third paragraph here."]
    text = "\n\n".join(paragraphs)
    sections = [TextSpan(text=text, location_ref="page 1")]
    # Big enough for the first two paragraphs packed together, not all three.
    chunk_size = len(paragraphs[0]) + 2 + len(paragraphs[1])

    chunks = chunk_sections(sections, chunk_size=chunk_size, overlap_ratio=0.1)

    assert all(len(chunk.text) <= chunk_size for chunk in chunks)
    assert all(chunk.location_ref == "page 1" for chunk in chunks)
    # every paragraph survives whole, inside some chunk — never split mid-paragraph
    for paragraph in paragraphs:
        assert any(paragraph in chunk.text for chunk in chunks)
    assert len(chunks) == 2


def test_chunk_sections_treats_a_markdown_heading_as_a_forced_boundary():
    heading = "# Title"
    intro = "Intro sentence right after the heading with no blank line in between."
    text = f"{heading}\n{intro}"
    sections = [TextSpan(text=text, location_ref="document")]
    # Big enough for either unit alone, one short of fitting both packed together.
    chunk_size = len(heading) + 2 + len(intro) - 1

    chunks = chunk_sections(sections, chunk_size=chunk_size, overlap_ratio=0.1)

    assert [c.text for c in chunks] == [heading, intro]
    assert all(chunk.location_ref == "document" for chunk in chunks)


def test_chunk_sections_merges_a_heading_with_short_following_text_when_it_fits():
    heading = "# Title"
    intro = "Short intro."
    text = f"{heading}\n{intro}"
    sections = [TextSpan(text=text, location_ref="document")]

    chunks = chunk_sections(sections, chunk_size=1000, overlap_ratio=0.1)

    assert len(chunks) == 1
    assert heading in chunks[0].text
    assert intro in chunks[0].text


def test_chunk_sections_falls_back_to_overlap_only_for_an_oversized_paragraph():
    short_paragraph = "Short lead-in."
    long_paragraph = "0123456789" * 6  # 60 chars, exceeds chunk_size below
    text = f"{short_paragraph}\n\n{long_paragraph}"
    sections = [TextSpan(text=text, location_ref="page 1")]

    chunks = chunk_sections(sections, chunk_size=20, overlap_ratio=0.5)

    # The short paragraph is never split or merged with the oversized one...
    assert chunks[0].text == short_paragraph
    # ...while the oversized paragraph, having no smaller boundary left to
    # respect, falls back to the fixed-size sliding-window overlap split.
    assert len(chunks) > 2
    assert all(len(chunk.text) <= 20 for chunk in chunks)
    assert chunks[-1].text[-1] == long_paragraph[-1]
