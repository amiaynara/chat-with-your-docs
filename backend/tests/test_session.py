"""API-seam tests for POST /session/reset (issue #30).

There's no separate ChatSession row (session_id is a bare column on Document/Message
— see models.py) and no explicit session lifecycle today: the cookie is a
non-expiring browser session cookie with no logout/reset. This endpoint ends the
current session for real — deletes its documents (object storage blob + cascade
chunks, same cleanup DELETE /documents/{id} already does) and messages, then clears
the cookie — rather than just cutting the cookie and leaving everything orphaned.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.adapters.retry import PermanentProviderError
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.repositories import DocumentRepository


def _get_object_storage_key(document_id: str) -> str:
    db = SessionLocal()
    try:
        document = DocumentRepository(db).get(uuid.UUID(document_id))
        assert document is not None
        return document.object_storage_key
    finally:
        db.close()


def test_reset_clears_documents_and_chat_history(client):
    client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    client.post("/chat/messages", json={"question": "anything?"})

    response = client.post("/session/reset")

    assert response.status_code == 204
    assert client.get("/documents").json() == []
    assert client.get("/chat/messages").json() == []


def test_reset_removes_the_documents_object_storage_blob(client, fake_object_storage):
    upload = client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    storage_key = _get_object_storage_key(upload.json()["id"])

    client.post("/session/reset")

    with pytest.raises(PermanentProviderError):
        fake_object_storage.get(storage_key)


def test_reset_issues_a_fresh_session_cookie(client):
    client.get("/documents")  # mint the initial cookie
    old_session_id = client.cookies.get(settings.session_cookie_name)
    assert old_session_id is not None

    client.post("/session/reset")
    client.get("/documents")  # mint the next one

    assert client.cookies.get(settings.session_cookie_name) != old_session_id


def test_reset_does_not_affect_another_sessions_documents(client):
    # `client` (the fixture) only needs to be requested to activate the fake
    # provider monkeypatches for this test function — both parties below are
    # their own, separately-cookied TestClient instances, same pattern as
    # test_chat_session_scoping.py.
    client = TestClient(app)
    other_client = TestClient(app)
    client.post("/documents", files={"file": ("mine.txt", b"hello", "text/plain")})
    other_client.post("/documents", files={"file": ("theirs.txt", b"hello", "text/plain")})

    client.post("/session/reset")

    assert len(other_client.get("/documents").json()) == 1
