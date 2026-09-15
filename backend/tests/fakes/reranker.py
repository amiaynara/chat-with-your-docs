from app.adapters.reranker import RankedDocument


class FakeRerankerProvider:
    """Deterministic word-overlap reranking — no real network calls.

    Scores each document by how many words it shares with the query, the same
    relevance signal the FakeLLMProvider and FakeEmbeddingProvider already use
    elsewhere in these tests, so pipeline tests can assert the reranked order
    without needing a live reranker model.
    """

    def __init__(self) -> None:
        self.last_query: str | None = None
        self.last_documents: list[str] | None = None

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[RankedDocument]:
        self.last_query = query
        self.last_documents = documents

        query_words = set(query.lower().split())
        scored = [
            RankedDocument(index=i, relevance_score=len(query_words & set(doc.lower().split())))
            for i, doc in enumerate(documents)
        ]
        scored.sort(key=lambda r: r.relevance_score, reverse=True)
        return scored[:top_n]
