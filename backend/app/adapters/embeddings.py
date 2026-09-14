from typing import Protocol

import openai

from app.adapters.retry import classify_provider_call, with_provider_retry

Vector = list[float]


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str
    # The length of the vectors `embed()` returns. Fixed per model, not a free
    # parameter — app.providers.get_embedding_provider() cross-checks this against
    # settings.embedding_dimensions (the width the `chunks.embedding` pgvector column
    # is actually provisioned for) and fails fast on mismatch, since a silent
    # mismatch would otherwise surface as an opaque DB error deep inside a Celery task.
    dimensions: int

    def embed(self, texts: list[str]) -> list[Vector]:
        """Embed a batch of texts, returning one vector per input text, in order."""
        ...


class OpenAIEmbeddingProvider:
    """Hosted embeddings via OpenAI. Needs OPENAI_API_KEY and API credits."""

    # Vector width is fixed per model, not a caller-supplied value — looked up here
    # rather than taking a `dimensions` constructor argument, so that
    # app.providers.get_embedding_provider()'s dimensions-consistency guard actually
    # catches a mismatch (e.g. EMBEDDING_MODEL switched to a different model without
    # updating EMBEDDING_DIMENSIONS) instead of trivially matching whatever config says.
    _MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str,
        model: str,
        model_version: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if model not in self._MODEL_DIMENSIONS:
            raise RuntimeError(
                f"Unknown OpenAI embedding model {model!r}; expected one of "
                f"{sorted(self._MODEL_DIMENSIONS)}."
            )
        self.model_name = model
        self.model_version = model_version
        self.dimensions = self._MODEL_DIMENSIONS[model]
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout_seconds)

    @with_provider_retry
    def embed(self, texts: list[str]) -> list[Vector]:
        response = classify_provider_call(
            lambda: self._client.embeddings.create(model=self.model_name, input=texts),
            transient_exceptions=(
                openai.RateLimitError,
                openai.APITimeoutError,
                openai.APIConnectionError,
            ),
            status_error_type=openai.APIStatusError,
        )
        return [item.embedding for item in response.data]


class LocalEmbeddingProvider:
    """Runs a local sentence-transformers model — no network call, no API key, no
    per-call cost. Trades some retrieval quality for zero external dependency; see
    docs/embeddings.md for the quality/latency comparison against the OpenAI adapter.

    `sentence-transformers`/torch are only imported here, inside __init__, rather than
    at module level — that import takes several seconds, and this class is only ever
    instantiated when EMBEDDING_PROVIDER=local, so the default (OpenAI) path never pays
    that startup cost.

    KNOWN LIMITATION (issue #20, deliberately left unfixed for now): providers.py
    constructs a new instance of this class on every call, so __init__'s ~40s
    torch-import + model-load cost repeats on every ingestion/query rather than being
    paid once per process. See docs/embeddings.md and the issue for the fix-vs-accept
    tradeoff before adding a process-level cache here.
    """

    def __init__(self, model_name: str, model_version: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model_version = model_version
        self._model = SentenceTransformer(model_name)
        # Inferred from the loaded model rather than hardcoded, so this stays correct
        # regardless of which sentence-transformers model LOCAL_EMBEDDING_MODEL names.
        dimensions = self._model.get_embedding_dimension()
        if dimensions is None:
            raise RuntimeError(
                f"Could not determine the output dimension of embedding model {model_name!r}."
            )
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[Vector]:
        # normalize_embeddings=True is BGE's documented recommended usage; harmless
        # here regardless, since retrieval compares vectors by cosine distance
        # (repositories.py), which is scale-invariant.
        return self._model.encode(texts, normalize_embeddings=True).tolist()
