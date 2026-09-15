import re

from app.ingestion.spans import TextSpan

# Paragraph breaks (blank lines) are the primary structural boundary, present
# regardless of source format. A Markdown heading line is always treated as its
# own boundary too, even when glued to surrounding text with no blank line —
# the one structural marker that appears directly in chunk *content* rather
# than in how parsing.py already sections a document (per-page for PDF, whole
# document for txt/md).
_BLANK_LINE_RE = re.compile(r"\n\s*\n")
_HEADING_LINE_RE = re.compile(r"(?m)^(#{1,6} .+)$")


def _split_into_units(text: str) -> list[str]:
    """Split text into paragraph/heading-sized structural units — the natural
    boundaries chunk packing prefers over an arbitrary character offset.
    """
    units: list[str] = []
    for block in _BLANK_LINE_RE.split(text):
        for piece in _HEADING_LINE_RE.split(block):
            piece = piece.strip()
            if piece:
                units.append(piece)
    return units


def _split_fixed(text: str, chunk_size: int, stride: int, location_ref: str) -> list[TextSpan]:
    """Fallback for a single structural unit that's still bigger than
    chunk_size on its own — a fixed-size sliding window with overlap, since
    there's no smaller structural boundary left to respect.
    """
    pieces: list[TextSpan] = []
    start = 0
    while start < len(text):
        pieces.append(TextSpan(text=text[start : start + chunk_size], location_ref=location_ref))
        if start + chunk_size >= len(text):
            break
        start += stride
    return pieces


def chunk_sections(
    sections: list[TextSpan], chunk_size: int, overlap_ratio: float
) -> list[TextSpan]:
    """Structure-aware chunking: pack paragraph/heading-sized units up to
    chunk_size, never splitting one mid-way — falling back to a fixed-size
    sliding window with overlap only for a single unit that's already bigger
    than chunk_size on its own, since there's no smaller boundary left to
    respect there.

    Chunk boundaries never cross a section boundary (one page, or the whole
    document for txt/md) — each section is packed independently.
    """
    overlap = int(chunk_size * overlap_ratio)
    stride = max(chunk_size - overlap, 1)

    chunks: list[TextSpan] = []
    for section in sections:
        buffer = ""
        for unit in _split_into_units(section.text):
            candidate = f"{buffer}\n\n{unit}" if buffer else unit
            if len(candidate) <= chunk_size:
                buffer = candidate
                continue

            if buffer:
                chunks.append(TextSpan(text=buffer, location_ref=section.location_ref))
                buffer = ""

            if len(unit) <= chunk_size:
                buffer = unit
            else:
                chunks.extend(_split_fixed(unit, chunk_size, stride, section.location_ref))

        if buffer:
            chunks.append(TextSpan(text=buffer, location_ref=section.location_ref))

    return chunks
