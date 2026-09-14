"""Unit tests for the EmbeddingProvider adapters with their real SDK/model client
mocked at the boundary — no real network call, no API key, no model download.

Error-classification behavior itself (which exception types map to
Transient/PermanentProviderError) is covered directly in test_retry.py; these just
prove each adapter wires its client correctly and returns embeddings in order on
success. The real local model is exercised separately, in the integration suite
(test_local_embedding_provider_integration.py).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.embeddings import LocalEmbeddingProvider, OpenAIEmbeddingProvider


def test_openai_embed_returns_one_vector_per_input_text_in_order():
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
    assert provider.dimensions == 1536


def test_openai_embed_reports_the_real_dimensions_for_a_different_known_model():
    provider = OpenAIEmbeddingProvider(
        api_key="fake-key", model="text-embedding-3-large", model_version="1"
    )

    assert provider.dimensions == 3072


def test_openai_provider_raises_for_an_unrecognized_model():
    with pytest.raises(RuntimeError, match="text-embedding-unknown"):
        OpenAIEmbeddingProvider(
            api_key="fake-key", model="text-embedding-unknown", model_version="1"
        )


def test_local_embed_returns_one_vector_per_input_text_in_order():
    mock_model = MagicMock()
    mock_model.get_embedding_dimension.return_value = 384
    mock_model.encode.return_value = SimpleNamespace(
        tolist=lambda: [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    )

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model) as mock_cls:
        provider = LocalEmbeddingProvider(model_name="BAAI/bge-small-en-v1.5", model_version="1")

    result = provider.embed(["first text", "second text"])

    mock_cls.assert_called_once_with("BAAI/bge-small-en-v1.5")
    mock_model.encode.assert_called_once_with(
        ["first text", "second text"], normalize_embeddings=True
    )
    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert provider.model_name == "BAAI/bge-small-en-v1.5"
    assert provider.model_version == "1"
    assert provider.dimensions == 384


def test_local_provider_raises_if_the_model_reports_no_dimension():
    mock_model = MagicMock()
    mock_model.get_embedding_dimension.return_value = None

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        with pytest.raises(RuntimeError, match="output dimension"):
            LocalEmbeddingProvider(model_name="some/weird-model", model_version="1")
