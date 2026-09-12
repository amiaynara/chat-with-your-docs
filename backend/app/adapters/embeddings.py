from typing import Protocol

import openai

from app.adapters.retry import classify_provider_call, with_provider_retry

Vector = list[float]


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str

    def embed(self, texts: list[str]) -> list[Vector]:
        """Embed a batch of texts, returning one vector per input text, in order."""
        ...


class OpenAIEmbeddingProvider:
    def __init__(
        self, api_key: str, model: str, model_version: str, timeout_seconds: float = 30.0
    ) -> None:
        self.model_name = model
        self.model_version = model_version
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
