"""API-seam tests for chat retrieval session scoping (issue #20).

`answer_question`'s retrieval path must never surface another anonymous
session's documents, even when the asking session hasn't scoped the question
to specific `doc_ids` — the session cookie is the only privacy boundary this
app has.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_chat_never_retrieves_or_cites_another_sessions_document(client):
    content = b"Routine onboarding notes. The secret launch code is Wobble-42. Keep it safe."
    client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})

    other_client = TestClient(app)
    other_client.post(
        "/documents",
        files={"file": ("garden.txt", b"Tomatoes need six hours of full sun daily.", "text/plain")},
    )

    response = other_client.post(
        "/chat/messages", json={"question": "What is the secret launch code?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "Wobble-42" not in body["answer"]
    assert body["citations"] == []
