"""API-seam tests for document-scoped retrieval filtering (issue #9)."""

from app import config


def test_scoped_question_only_returns_citations_from_the_selected_document(client):
    doc_a = client.post(
        "/documents", files={"file": ("a.txt", b"Doc A fact: the sky is blue.", "text/plain")}
    )
    client.post(
        "/documents", files={"file": ("b.txt", b"Doc B fact: the sky is blue too.", "text/plain")}
    )
    doc_a_id = doc_a.json()["id"]

    response = client.post(
        "/chat/messages",
        json={"question": "What color is the sky?", "doc_ids": [doc_a_id]},
    )

    assert response.status_code == 200
    citations = response.json()["citations"]
    assert citations
    assert all(c["document_id"] == doc_a_id for c in citations)


def test_document_scope_filters_inside_the_retrieval_query_not_via_post_filtering(
    client, monkeypatch
):
    # A decoy document whose content near-verbatim echoes the question — under the
    # fake (bag-of-words) embedding this scores as MORE similar to the query than
    # the actual target document, so it alone would occupy the only (patched down
    # to 1) top-k slot in an *unscoped* search, crowding the target out entirely.
    client.post(
        "/documents",
        files={
            "file": (
                "decoy.txt",
                b"What is the secret launch code? What is the secret launch code?",
                "text/plain",
            )
        },
    )
    target_upload = client.post(
        "/documents",
        files={"file": ("target.txt", b"The secret launch code is Wobble-42.", "text/plain")},
    )
    target_id = target_upload.json()["id"]

    monkeypatch.setattr(config.settings, "retrieval_top_k", 1)

    response = client.post(
        "/chat/messages",
        json={"question": "What is the secret launch code?", "doc_ids": [target_id]},
    )

    # A post-filter implementation would fetch the unscoped top-1 (the decoy),
    # discover it doesn't belong to doc_ids, and refuse with no evidence. Filtering
    # inside the query instead correctly finds the target document's own chunk.
    assert response.status_code == 200
    body = response.json()
    assert "wobble-42" in body["answer"].lower()
    assert len(body["citations"]) == 1
    assert body["citations"][0]["document_id"] == target_id
