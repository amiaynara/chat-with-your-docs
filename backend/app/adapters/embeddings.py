from typing import Protocol

import openai

from app.adapters.retry import PermanentProviderError, TransientProviderError, with_provider_retry

Vector = list[float]


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str

    def embed(self, texts: list[str]) -> list[Vector]:
        """Embed a batch of texts, returning one vector per input text, in order."""
        ...


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str, model_version: str) -> None:
        self.model_name = model
        self.model_version = model_version
        self._client = openai.OpenAI(api_key=api_key)

    @with_provider_retry
    def embed(self, texts: list[str]) -> list[Vector]:
        try:
            response = self._client.embeddings.create(model=self.model_name, input=texts)
        except openai.RateLimitError as exc:
            raise TransientProviderError(str(exc)) from exc
        except openai.APITimeoutError as exc:
            raise TransientProviderError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise TransientProviderError(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientProviderError(str(exc)) from exc
            raise PermanentProviderError(str(exc)) from exc
        return [item.embedding for item in response.data]
