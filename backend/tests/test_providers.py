"""Unit tests for providers.py's own wiring — not the adapters themselves.

Each get_*() function is stubbed at the class it constructs, so these assert
"providers.py passes the right settings to the right adapter" without needing
a live network connection. The adapters' own behavior (real client calls,
error classification) is covered separately in their own test modules.
"""

import pytest

from app import providers
from app.config import settings


def test_get_object_storage_wires_settings_into_s3_object_storage(monkeypatch):
    captured = {}

    class StubStorage:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(providers, "S3ObjectStorage", StubStorage)

    result = providers.get_object_storage()

    assert isinstance(result, StubStorage)
    assert captured == {
        "endpoint_url": settings.object_storage_endpoint_url,
        "access_key": settings.object_storage_access_key,
        "secret_key": settings.object_storage_secret_key,
        "bucket": settings.object_storage_bucket,
        "timeout_seconds": settings.provider_timeout_seconds,
    }


def test_get_embedding_provider_wires_settings_into_openai_embedding_provider(monkeypatch):
    captured = {}

    class StubEmbedding:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model_name = kwargs["model"]
            # A real OpenAIEmbeddingProvider looks its dimensions up from its own
            # known-model table (see embeddings.py), not from a constructor arg; this
            # stub just needs to match the configured DB column width so the
            # consistency guard passes.
            self.dimensions = settings.embedding_dimensions

    monkeypatch.setattr(providers, "OpenAIEmbeddingProvider", StubEmbedding)
    monkeypatch.setattr(settings, "embedding_provider", "openai")

    result = providers.get_embedding_provider()

    assert isinstance(result, StubEmbedding)
    assert captured == {
        "api_key": settings.openai_api_key,
        "model": settings.embedding_model,
        "model_version": settings.embedding_model_version,
        "timeout_seconds": settings.provider_timeout_seconds,
    }


def test_get_embedding_provider_wires_settings_into_local_embedding_provider(monkeypatch):
    captured = {}

    class StubLocalEmbedding:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model_name = kwargs["model_name"]
            # A real local model reports its own dimensions; this stub just needs to
            # match the configured DB column width so the consistency guard passes.
            self.dimensions = settings.embedding_dimensions

    monkeypatch.setattr(providers, "LocalEmbeddingProvider", StubLocalEmbedding)
    monkeypatch.setattr(settings, "embedding_provider", "local")

    result = providers.get_embedding_provider()

    assert isinstance(result, StubLocalEmbedding)
    assert captured == {
        "model_name": settings.local_embedding_model,
        "model_version": settings.local_embedding_model_version,
    }


def test_get_embedding_provider_raises_on_unknown_provider_name(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "bogus")

    with pytest.raises(RuntimeError, match="Unknown EMBEDDING_PROVIDER"):
        providers.get_embedding_provider()


def test_get_embedding_provider_raises_when_dimensions_dont_match_the_db_column(monkeypatch):
    class StubEmbedding:
        def __init__(self, **kwargs):
            self.model_name = "some-model"
            self.dimensions = 999  # deliberately inconsistent with settings.embedding_dimensions

    monkeypatch.setattr(providers, "OpenAIEmbeddingProvider", StubEmbedding)
    monkeypatch.setattr(settings, "embedding_provider", "openai")

    with pytest.raises(RuntimeError, match="EMBEDDING_DIMENSIONS"):
        providers.get_embedding_provider()


def test_get_llm_provider_wires_settings_into_anthropic_llm_provider(monkeypatch):
    captured = {}

    class StubLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(providers, "AnthropicLLMProvider", StubLLM)
    monkeypatch.setattr(settings, "llm_provider", "anthropic")

    result = providers.get_llm_provider()

    assert isinstance(result, StubLLM)
    assert captured == {
        "api_key": settings.anthropic_api_key,
        "model": settings.llm_model,
        "timeout_seconds": settings.provider_timeout_seconds,
    }


def test_get_llm_provider_wires_settings_into_gemini_llm_provider(monkeypatch):
    captured = {}

    class StubLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(providers, "GeminiLLMProvider", StubLLM)
    monkeypatch.setattr(settings, "llm_provider", "google")

    result = providers.get_llm_provider()

    assert isinstance(result, StubLLM)
    assert captured == {
        "api_key": settings.google_api_key,
        "model": settings.google_llm_model,
        "timeout_seconds": settings.provider_timeout_seconds,
    }


def test_get_llm_provider_raises_on_unknown_provider_name(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bogus")

    with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER"):
        providers.get_llm_provider()
