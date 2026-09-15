from dataclasses import dataclass
from typing import Protocol

import cohere
import httpx
from cohere.core.api_error import ApiError as CohereApiError

from app.adapters.retry import classify_provider_call, with_provider_retry


@dataclass
class RankedDocument:
    # Index back into the `documents` list passed to rerank() — not a chunk/db id,
    # since the reranker only ever sees plain text, not our domain objects.
    index: int
    relevance_score: float


class RerankerProvider(Protocol):
    def rerank(self, query: str, documents: list[str], top_n: int) -> list[RankedDocument]:
        """Re-score `documents` against `query`, returning up to `top_n` results
        ordered by relevance (highest first)."""
        ...


class CohereRerankProvider:
    """Hosted reranking via Cohere's Rerank API. Needs COHERE_API_KEY."""

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self._model = model
        self._client = cohere.ClientV2(api_key=api_key, timeout=timeout_seconds)

    @with_provider_retry
    def rerank(self, query: str, documents: list[str], top_n: int) -> list[RankedDocument]:
        response = classify_provider_call(
            lambda: self._client.rerank(
                model=self._model, query=query, documents=documents, top_n=top_n
            ),
            # Cohere's SDK is httpx-based like google-genai's (docs/llm-providers.md)
            # and likewise has no distinct RateLimitError/APITimeoutError types of its
            # own for transport-level failures — those surface as raw httpx
            # exceptions, while HTTP-status failures (429/5xx/4xx) arrive as
            # cohere.errors.* subclasses of the shared ApiError, each already
            # carrying the right `.status_code` (e.g. TooManyRequestsError is always
            # 429) — exactly what classify_provider_call's status_error_type
            # classification (default status_code_attr="status_code") expects.
            transient_exceptions=(httpx.ConnectError, httpx.TimeoutException),
            status_error_type=CohereApiError,
        )
        return [
            RankedDocument(index=result.index, relevance_score=result.relevance_score)
            for result in response.results
        ]
