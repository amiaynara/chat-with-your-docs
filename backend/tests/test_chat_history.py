"""API-seam tests for multi-turn conversation + session persistence (issue #8)."""

from app import config


def test_first_chat_message_gets_an_anonymous_session_cookie(client):
    response = client.post("/chat/messages", json={"question": "anything?"})

    assert config.settings.session_cookie_name in response.cookies


def test_message_history_persists_across_requests_like_a_page_refresh(client):
    content = b"The secret launch code is Wobble-42."
    client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})

    client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    history = client.get("/chat/messages").json()

    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "What is the secret launch code?"
    assert history[0]["citations"] is None
    assert "Wobble-42" in history[1]["content"]
    assert history[1]["citations"]
    assert history[1]["citations"][0]["filename"] == "notes.txt"


def test_message_history_is_scoped_to_the_session(client):
    client.post("/chat/messages", json={"question": "anything?"})

    from fastapi.testclient import TestClient

    from app.main import app

    other_client = TestClient(app)
    assert other_client.get("/chat/messages").json() == []


def test_followup_question_includes_recent_conversation_history(client, fake_llm_provider):
    content = b"The secret launch code is Wobble-42."
    client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})

    client.post("/chat/messages", json={"question": "What is the secret launch code?"})
    # Still shares enough vocabulary with the document to clear the retrieval
    # guardrail (#6) on its own — a follow-up needing conversation history to be
    # *retrieved* at all (e.g. "Can you repeat that?") is a query-rewriting
    # concern beyond this ticket's "include recent turns in the prompt" ask.
    followup = "What was the secret launch code again?"
    client.post("/chat/messages", json={"question": followup})

    messages = fake_llm_provider.last_messages
    assert messages is not None
    assert messages[0].role == "user"
    assert "secret launch code" in messages[0].content
    assert messages[1].role == "assistant"
    assert "Wobble-42" in messages[1].content
    assert messages[-1].role == "user"
    assert messages[-1].content == followup


def test_asking_with_no_documents_prompts_upload_without_attempting_to_answer(
    client, fake_llm_provider
):
    response = client.post("/chat/messages", json={"question": "anything?"})

    assert response.status_code == 200
    body = response.json()
    assert "upload" in body["answer"].lower()
    assert body["citations"] == []
    assert fake_llm_provider.last_system is None

    history = client.get("/chat/messages").json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert "upload" in history[1]["content"].lower()
