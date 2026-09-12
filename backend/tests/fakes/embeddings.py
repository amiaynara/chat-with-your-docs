import hashlib
import math

from app.config import settings


def _bucket(token: str, dim: int) -> int:
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % dim


class FakeEmbeddingProvider:
    """Deterministic bag-of-words hashing embedding — no real network calls.

    Cosine similarity between two fake embeddings tracks shared vocabulary,
    so retrieval tests can assert that a query surfaces the chunk containing
    matching words, without needing a real embedding model. Dimension matches
    the real provider's so it fits the same pgvector column in tests.
    """

    def __init__(self, dim: int = settings.embedding_dimensions) -> None:
        self.model_name = "fake-embedding"
        self.model_version = "test"
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for token in text.lower().split():
            vector[_bucket(token, self._dim)] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
