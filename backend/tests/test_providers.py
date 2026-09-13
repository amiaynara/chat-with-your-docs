"""Unit tests for providers.py's own wiring — not the adapters themselves.

Each get_*() function is stubbed at the class it constructs, so these assert
"providers.py passes the right settings to the right adapter" without needing
a live network connection. The adapters' own behavior (real client calls,
error classification) is covered separately in their own test modules.
"""

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

    monkeypatch.setattr(providers, "OpenAIEmbeddingProvider", StubEmbedding)

    result = providers.get_embedding_provider()

    assert isinstance(result, StubEmbedding)
    assert captured == {
        "api_key": settings.openai_api_key,
        "model": settings.embedding_model,
        "model_version": settings.embedding_model_version,
        "timeout_seconds": settings.provider_timeout_seconds,
    }


def test_get_llm_provider_wires_settings_into_anthropic_llm_provider(monkeypatch):
    captured = {}

    class StubLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(providers, "AnthropicLLMProvider", StubLLM)

    result = providers.get_llm_provider()

    assert isinstance(result, StubLLM)
    assert captured == {
        "api_key": settings.anthropic_api_key,
        "timeout_seconds": settings.provider_timeout_seconds,
    }
