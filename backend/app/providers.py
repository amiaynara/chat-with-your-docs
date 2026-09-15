"""Resolves the configured provider adapter for each external dependency.

Tests monkeypatch these functions to return fakes instead of constructing
real network-backed clients — see tests/conftest.py.
"""

from app.adapters.embeddings import (
    EmbeddingProvider,
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from app.adapters.llm import AnthropicLLMProvider, GeminiLLMProvider, LLMProvider
from app.adapters.reranker import CohereRerankProvider, RerankerProvider
from app.adapters.secrets import AWSSecretManager, LocalSecretManager, SecretManager
from app.adapters.storage import ObjectStorage, S3ObjectStorage
from app.config import settings


def get_object_storage() -> ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=settings.object_storage_endpoint_url,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        bucket=settings.object_storage_bucket,
        timeout_seconds=settings.provider_timeout_seconds,
    )


def get_embedding_provider() -> EmbeddingProvider:
    provider: EmbeddingProvider
    if settings.embedding_provider == "local":
        provider = LocalEmbeddingProvider(
            model_name=settings.local_embedding_model,
            model_version=settings.local_embedding_model_version,
        )
    elif settings.embedding_provider == "openai":
        provider = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            model_version=settings.embedding_model_version,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    else:
        raise RuntimeError(
            f"Unknown EMBEDDING_PROVIDER={settings.embedding_provider!r}; expected "
            "'openai' or 'local'."
        )

    if provider.dimensions != settings.embedding_dimensions:
        raise RuntimeError(
            f"EMBEDDING_PROVIDER={settings.embedding_provider!r} ({provider.model_name}) "
            f"produces {provider.dimensions}-dim vectors, but EMBEDDING_DIMENSIONS is set to "
            f"{settings.embedding_dimensions}. The `chunks.embedding` column is a fixed-width "
            "pgvector column, so switching providers to a model with a different output size "
            "requires updating EMBEDDING_DIMENSIONS, running a migration to resize the column, "
            "and re-ingesting existing documents — see docs/embeddings.md."
        )

    return provider


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "google":
        return GeminiLLMProvider(
            api_key=settings.google_api_key,
            model=settings.google_llm_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    elif settings.llm_provider == "anthropic":
        return AnthropicLLMProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER={settings.llm_provider!r}; expected 'anthropic' or 'google'."
        )


def get_reranker_provider() -> RerankerProvider:
    return CohereRerankProvider(
        api_key=settings.cohere_api_key,
        model=settings.reranker_model,
        timeout_seconds=settings.provider_timeout_seconds,
    )


def get_secret_manager() -> SecretManager:
    if settings.secret_manager == "local":
        return LocalSecretManager(file_path=settings.local_secrets_file)
    elif settings.secret_manager == "aws":
        return AWSSecretManager(
            region=settings.aws_secrets_region,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    else:
        raise RuntimeError(
            f"Unknown SECRET_MANAGER={settings.secret_manager!r}; expected 'local' or 'aws'."
        )
