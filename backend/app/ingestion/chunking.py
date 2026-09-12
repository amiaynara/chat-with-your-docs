from app.ingestion.spans import TextSpan


def chunk_sections(
    sections: list[TextSpan], chunk_size: int, overlap_ratio: float
) -> list[TextSpan]:
    """Naive fixed-size chunking with overlap, within each parsed section.

    A starting hypothesis (structure-aware chunking respecting paragraph/heading
    boundaries is a later, evidence-driven upgrade — see ticket #9).
    """
    overlap = int(chunk_size * overlap_ratio)
    stride = max(chunk_size - overlap, 1)

    chunks: list[TextSpan] = []
    for section in sections:
        text = section.text
        if len(text) <= chunk_size:
            chunks.append(TextSpan(text=text, location_ref=section.location_ref))
            continue

        start = 0
        while start < len(text):
            piece = text[start : start + chunk_size]
            chunks.append(TextSpan(text=piece, location_ref=section.location_ref))
            if start + chunk_size >= len(text):
                break
            start += stride

    return chunks
