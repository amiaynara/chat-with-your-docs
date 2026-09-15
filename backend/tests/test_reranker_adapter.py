"""Unit tests for the RerankerProvider adapter with its real SDK client mocked at the
boundary — no real network call, no API key needed.

Error-classification behavior itself is covered directly in test_retry.py; these just
prove rerank() assembles the request and extracts the response correctly on success.
"""

from types import SimpleNamespace

from app.adapters.reranker import CohereRerankProvider


def test_rerank_returns_index_and_relevance_score_in_response_order():
    provider = CohereRerankProvider(api_key="fake-key", model="rerank-v3.5")

    fake_response = SimpleNamespace(
        results=[
            SimpleNamespace(index=2, relevance_score=0.9),
            SimpleNamespace(index=0, relevance_score=0.4),
        ]
    )
    captured = {}

    def _fake_rerank(**kwargs):
        captured.update(kwargs)
        return fake_response

    provider._client.rerank = _fake_rerank

    result = provider.rerank(
        query="What is the warranty?",
        documents=["doc a", "doc b", "doc c"],
        top_n=2,
    )

    assert captured["model"] == "rerank-v3.5"
    assert captured["query"] == "What is the warranty?"
    assert captured["documents"] == ["doc a", "doc b", "doc c"]
    assert captured["top_n"] == 2
    assert [(r.index, r.relevance_score) for r in result] == [(2, 0.9), (0, 0.4)]
