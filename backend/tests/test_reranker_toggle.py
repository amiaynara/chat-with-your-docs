"""API-seam tests for the optional reranker pipeline toggle (issue #12)."""

from app import config


def test_same_question_answers_successfully_with_the_reranker_off(client):
    content = b"The secret launch code is Wobble-42."
    client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    assert "Wobble-42" in response.json()["answer"]


def test_same_question_answers_successfully_with_the_reranker_on(
    client, fake_reranker_provider, monkeypatch
):
    monkeypatch.setattr(config.settings, "reranker_enabled", True)
    content = b"The secret launch code is Wobble-42."
    client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    assert "Wobble-42" in response.json()["answer"]
    # Proves the rerank step actually ran, not just that the toggle was a no-op.
    assert fake_reranker_provider.last_query == "What is the secret launch code?"
    assert fake_reranker_provider.last_documents


def test_reranker_reorders_candidates_so_the_top_scored_chunk_is_answered_from(
    client, fake_reranker_provider, monkeypatch
):
    monkeypatch.setattr(config.settings, "reranker_enabled", True)
    # Both documents share heavy vocabulary overlap with the question and with each
    # other under the fake (bag-of-words) embedding, so vector distance alone won't
    # reliably separate them — but the fake reranker's own word-overlap scoring
    # (tests/fakes/reranker.py) ranks the doc that answers the *specific* question
    # above the generic one, and the fake LLM only ever sees whatever the reranked
    # pipeline puts in front of it.
    client.post(
        "/documents",
        files={
            "file": (
                "codes.txt",
                b"Base facility access codes rotate weekly for general security.",
                "text/plain",
            )
        },
    )
    client.post(
        "/documents",
        files={
            "file": (
                "launch.txt",
                b"The secret launch code is Wobble-42.",
                "text/plain",
            )
        },
    )

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    assert "Wobble-42" in response.json()["answer"]
