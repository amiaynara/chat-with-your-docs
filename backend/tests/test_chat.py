def test_answer_is_grounded_in_a_fact_only_present_in_the_uploaded_document(client):
    content = b"Routine onboarding notes. The secret launch code is Wobble-42. Keep it safe."
    upload = client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})
    assert upload.status_code == 201

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    assert "Wobble-42" in response.json()["answer"]


def test_answer_with_no_documents_does_not_fabricate_information(client):
    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    answer = response.json()["answer"].lower()
    assert "wobble" not in answer


def test_answer_includes_a_citation_pointing_at_the_supporting_document(client):
    content = b"Routine onboarding notes. The secret launch code is Wobble-42. Keep it safe."
    upload = client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})
    document_id = upload.json()["id"]

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    citations = response.json()["citations"]
    assert len(citations) >= 1
    citation = citations[0]
    assert citation["document_id"] == document_id
    assert citation["filename"] == "notes.txt"
    assert citation["location_ref"] == "document"
    assert "Wobble-42" in citation["snippet"]


def test_answer_with_no_documents_has_no_citations(client):
    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    assert response.json()["citations"] == []


def test_citation_snippet_is_truncated_for_a_long_supporting_chunk(client):
    # The secret launch code sentence is pushed past the 240-char snippet cap by
    # leading filler text sharing "secret"/"launch"/"code" words, so the fake
    # (word-overlap) embedding still retrieves this chunk as the top match.
    filler = "Secret launch code briefing. " * 10
    content = (filler + "The secret launch code is Wobble-42. Keep it safe.").encode()
    client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    snippet = response.json()["citations"][0]["snippet"]
    assert len(snippet) == 241  # 240 chars + the truncation ellipsis
    assert snippet.endswith("…")


def test_llm_provider_failure_returns_a_clean_error_not_a_bare_500(client, fake_llm_provider):
    # A relevant document must exist, or the no-evidence guardrail refuses before
    # the LLM is ever called — this test is specifically about a failure *from* the
    # LLM call, so retrieval must actually reach it.
    content = b"The secret launch code is Wobble-42."
    client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})

    def _boom(*args, **kwargs):
        raise RuntimeError("provider misconfigured: leaked internal detail")

    fake_llm_provider.generate = _boom

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "try again" in detail.lower()
    assert "leaked internal detail" not in detail
