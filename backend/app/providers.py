"""Resolves the configured provider adapter for each external dependency.

Tests monkeypatch these functions to return fakes instead of constructing
real network-backed clients — see tests/conftest.py.
"""

from app.adapters.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from app.adapters.llm import AnthropicLLMProvider, LLMProvider
from app.adapters.storage import ObjectStorage, S3ObjectStorage
from app.config import settings


def get_object_storage() -> ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=settings.object_storage_endpoint_url,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        bucket=settings.object_storage_bucket,
    )


def get_embedding_provider() -> EmbeddingProvider:
    return OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        model_version=settings.embedding_model_version,
    )


def get_llm_provider() -> LLMProvider:
    return AnthropicLLMProvider(api_key=settings.anthropic_api_key)
