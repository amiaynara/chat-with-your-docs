import hashlib
import math

# Matches the `chunks.embedding` column width the real (Alembic-migrated) test
# database is actually built with — see alembic/versions/0002_documents_and_chunks.py,
# which hardcodes this same 384 rather than reading it from settings, for the same
# reason: the migration is the versioned source of truth for the column's real width,
# independent of whatever a developer's local .env happens to set
# settings.embedding_dimensions to (e.g. 1536, when EMBEDDING_PROVIDER=openai). Defaulting
# this fake to settings.embedding_dimensions previously coupled it to that mutable local
# config instead, so a local .env override silently broke every test that inserts a
# fake embedding (PendingRollbackError from a pgvector dimension mismatch).
_TEST_DB_EMBEDDING_DIMENSIONS = 384


def _bucket(token: str, dim: int) -> int:
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % dim


class FakeEmbeddingProvider:
    """Deterministic bag-of-words hashing embedding — no real network calls.

    Cosine similarity between two fake embeddings tracks shared vocabulary,
    so retrieval tests can assert that a query surfaces the chunk containing
    matching words, without needing a real embedding model. Dimension matches
    the real (migrated) pgvector column so it fits in tests.
    """

    def __init__(self, dim: int = _TEST_DB_EMBEDDING_DIMENSIONS) -> None:
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
