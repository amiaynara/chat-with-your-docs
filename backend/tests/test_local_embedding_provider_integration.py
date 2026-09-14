"""Contract test for the real LocalEmbeddingProvider — actually loads
BAAI/bge-small-en-v1.5 via sentence-transformers and runs it.

Marked `integration` (excluded from the default `-m 'not integration'` run — see
pyproject.toml) since this downloads real model weights on first run (~130MB from
Hugging Face Hub) and does real (CPU) inference: run with `uv run pytest -m
integration`. Mirrors test_storage_adapter.py's real-MinIO contract test — real
adapter, real dependency, no fakes, kept out of the fast default suite.
"""

import pytest

from app.adapters.embeddings import LocalEmbeddingProvider


@pytest.mark.integration
def test_embed_produces_vectors_of_the_advertised_dimension():
    provider = LocalEmbeddingProvider(model_name="BAAI/bge-small-en-v1.5", model_version="1")

    vectors = provider.embed(["hello world", "a second sentence"])

    assert len(vectors) == 2
    assert all(len(vector) == provider.dimensions for vector in vectors)


@pytest.mark.integration
def test_embed_places_semantically_similar_sentences_closer_together():
    """Sanity check that this is a genuine semantic model, not just a hash:
    two paraphrases of the same idea should be closer (by cosine similarity)
    than either is to an unrelated sentence.
    """
    provider = LocalEmbeddingProvider(model_name="BAAI/bge-small-en-v1.5", model_version="1")

    a, b, unrelated = provider.embed(
        [
            "The cat sat on the mat.",
            "A cat was sitting on a mat.",
            "Quarterly revenue exceeded analyst expectations.",
        ]
    )

    def cosine_similarity(x: list[float], y: list[float]) -> float:
        dot = sum(xi * yi for xi, yi in zip(x, y, strict=True))
        norm_x = sum(xi * xi for xi in x) ** 0.5
        norm_y = sum(yi * yi for yi in y) ** 0.5
        return dot / (norm_x * norm_y)

    assert cosine_similarity(a, b) > cosine_similarity(a, unrelated)
