"""API-seam tests for hybrid (vector + keyword) retrieval (issue #11)."""

from app import config


def test_keyword_only_match_is_surfaced_when_vector_search_alone_would_miss_it(client):
    # The fake embedding (tests/fakes/embeddings.py) is a per-token bag-of-words hash:
    # two different word *forms* land in different hash buckets and so are orthogonal
    # (~max cosine distance), even though Postgres's English text-search config stems
    # both to the same lexeme. "warranties" (document) vs. "warranty" (question) is
    # exactly that case — a real keyword search finds it; the fake vector embedding
    # alone cannot.
    content = b"Company policy: all hardware warranties last for two full years."
    client.post("/documents", files={"file": ("policy.txt", content, "text/plain")})

    response = client.post(
        "/chat/messages", json={"question": "How long is the warranty?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "two full years" in body["answer"].lower()
    citations = response.json()["citations"]
    assert citations
    assert citations[0]["filename"] == "policy.txt"


def test_combined_vector_and_keyword_candidates_stay_capped_at_retrieval_top_k(
    client, monkeypatch
):
    # Each branch (vector, keyword) is independently capped at retrieval_top_k inside
    # search_ready — without a cap on their *union* too, a query that pulls a full
    # retrieval_top_k from each branch could send up to 2x retrieval_top_k chunks to
    # the LLM. vector.txt/vector2.txt share only stopwords ("what is the") with the
    # question under the fake bag-of-words embedding, so they're vector-relevant but
    # contain neither "return" nor "policy"/its stem — no keyword match. returning.txt/
    # policies.txt are the mirror image: "returning"/"policies" stem to the question's
    # own lexemes (a real Postgres keyword match) but share no literal words with the
    # question at all under the fake embedding, so vector distance is maximal (not
    # vector-relevant). All four clear the relevance guardrail (by distance or by
    # keyword match), giving 4 distinct relevant candidates against a top_k of 2.
    monkeypatch.setattr(config.settings, "retrieval_top_k", 2)
    client.post(
        "/documents",
        files={"file": ("vector.txt", b"What is the wobble zephyr?", "text/plain")},
    )
    client.post(
        "/documents",
        files={"file": ("vector2.txt", b"What is the gadget norple?", "text/plain")},
    )
    client.post(
        "/documents",
        files={
            "file": (
                "returning.txt",
                b"Item returning process details for warehouse staff only.",
                "text/plain",
            )
        },
    )
    client.post(
        "/documents",
        files={
            "file": (
                "policies.txt",
                b"Vendor policies audit schedule for quarterly compliance review.",
                "text/plain",
            )
        },
    )

    response = client.post("/chat/messages", json={"question": "What is the return policy?"})

    assert response.status_code == 200
    citations = response.json()["citations"]
    assert len(citations) == 2
