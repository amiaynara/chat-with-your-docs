from dataclasses import dataclass


@dataclass
class TextSpan:
    """A span of text tagged with where it came from in the source document.

    Used both for a parsed section (e.g. one PDF page) and for a chunk carved
    out of one — the shape is the same at both stages of the pipeline.
    """

    text: str
    location_ref: str
