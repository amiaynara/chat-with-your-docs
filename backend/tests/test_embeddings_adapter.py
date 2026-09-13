"""Unit tests for OpenAIEmbeddingProvider with the openai client mocked at
the SDK boundary — no real network call, no API key needed.

Error-classification behavior itself (which exception types map to
Transient/PermanentProviderError) is covered directly in test_retry.py;
this just proves embed() wires classify_provider_call correctly and
returns embeddings in order on success.
"""

from types import SimpleNamespace

from app.adapters.embeddings import OpenAIEmbeddingProvider


def test_embed_returns_one_vector_per_input_text_in_order():
    provider = OpenAIEmbeddingProvider(
        api_key="fake-key", model="text-embedding-3-small", model_version="1"
    )

    fake_response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2]), SimpleNamespace(embedding=[0.3, 0.4])]
    )
    provider._client.embeddings.create = lambda **kwargs: fake_response

    result = provider.embed(["first text", "second text"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert provider.model_name == "text-embedding-3-small"
    assert provider.model_version == "1"
