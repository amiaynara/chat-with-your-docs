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


def test_llm_provider_failure_returns_a_clean_error_not_a_bare_500(client, fake_llm_provider):
    def _boom(*args, **kwargs):
        raise RuntimeError("provider misconfigured: leaked internal detail")

    fake_llm_provider.generate = _boom

    response = client.post("/chat/messages", json={"question": "anything?"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "try again" in detail.lower()
    assert "leaked internal detail" not in detail
