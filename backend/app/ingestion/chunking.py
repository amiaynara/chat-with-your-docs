from app.ingestion.parsing import Section


class TextChunk:
    def __init__(self, text: str, location_ref: str) -> None:
        self.text = text
        self.location_ref = location_ref


def chunk_sections(
    sections: list[Section], chunk_size: int, overlap_ratio: float
) -> list[TextChunk]:
    """Naive fixed-size chunking with overlap, within each parsed section.

    A starting hypothesis (structure-aware chunking respecting paragraph/heading
    boundaries is a later, evidence-driven upgrade — see ticket #9).
    """
    overlap = int(chunk_size * overlap_ratio)
    stride = max(chunk_size - overlap, 1)

    chunks: list[TextChunk] = []
    for section in sections:
        text = section.text
        if len(text) <= chunk_size:
            chunks.append(TextChunk(text=text, location_ref=section.location_ref))
            continue

        start = 0
        while start < len(text):
            piece = text[start : start + chunk_size]
            chunks.append(TextChunk(text=piece, location_ref=section.location_ref))
            if start + chunk_size >= len(text):
                break
            start += stride

    return chunks
