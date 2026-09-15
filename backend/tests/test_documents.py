import uuid

import pytest

from app import config
from app.adapters.retry import PermanentProviderError, TransientProviderError
from app.db import SessionLocal
from app.repositories import DocumentRepository


def test_upload_txt_document_reaches_ready_and_is_listed(client):
    content = b"The secret launch code is Wobble-42. Keep it confidential."
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", content, "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["format"] == "txt"

    documents = client.get("/documents").json()
    assert len(documents) == 1
    assert documents[0]["id"] == body["id"]
    assert documents[0]["status"] == "ready"
    assert documents[0]["error_reason"] is None


def test_upload_corrupt_pdf_reaches_failed_with_reason(client):
    response = client.post(
        "/documents",
        files={"file": ("broken.pdf", b"not actually a pdf", "application/pdf")},
    )

    assert response.status_code == 201
    document_id = response.json()["id"]

    documents = client.get("/documents").json()
    document = next(d for d in documents if d["id"] == document_id)
    assert document["status"] == "failed"
    assert document["error_reason"]


def test_upload_rejects_missing_filename(client):
    # httpx's `files=` convenience wrapper won't send a blank filename, so a
    # raw multipart body is built to reach a client that does (a genuine
    # edge case a malformed or adversarial client could trigger).
    boundary = "boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename=""\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "whatever\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    response = client.post(
        "/documents",
        content=body,
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 422
    assert "filename" in response.json()["detail"]


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/documents",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_upload_rejects_unsupported_file_type_before_any_ingestion(client):
    response = client.post(
        "/documents",
        files={"file": ("virus.exe", b"whatever", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert client.get("/documents").json() == []


def test_upload_rejects_oversized_file_before_any_ingestion(
    client, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config.settings, "max_upload_bytes", 10)

    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"this file is definitely over ten bytes", "text/plain")},
    )

    assert response.status_code == 422
    assert client.get("/documents").json() == []


def test_transient_object_storage_error_returns_503(client, fake_object_storage):
    def _boom(key, data):
        raise TransientProviderError("minio is momentarily unreachable")

    fake_object_storage.put = _boom

    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


def test_permanent_object_storage_error_returns_502(client, fake_object_storage):
    def _boom(key, data):
        raise PermanentProviderError("bad credentials")

    fake_object_storage.put = _boom

    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 502
    assert "credentials/configuration" in response.json()["detail"]


def test_documents_are_scoped_to_the_uploading_session(client):
    client.post("/documents", files={"file": ("a.txt", b"hello world", "text/plain")})

    from fastapi.testclient import TestClient

    from app.main import app

    other_client = TestClient(app)
    assert other_client.get("/documents").json() == []


def _get_object_storage_key(document_id: str) -> str:
    db = SessionLocal()
    try:
        document = DocumentRepository(db).get(uuid.UUID(document_id))
        assert document is not None
        return document.object_storage_key
    finally:
        db.close()


def test_delete_document_removes_it_from_the_list(client):
    upload = client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    document_id = upload.json()["id"]

    response = client.delete(f"/documents/{document_id}")

    assert response.status_code == 204
    assert client.get("/documents").json() == []


def test_delete_document_removes_its_blob_from_object_storage(client, fake_object_storage):
    upload = client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    document_id = upload.json()["id"]
    storage_key = _get_object_storage_key(document_id)

    response = client.delete(f"/documents/{document_id}")

    assert response.status_code == 204
    with pytest.raises(PermanentProviderError):
        fake_object_storage.get(storage_key)


def test_deleted_documents_chunks_no_longer_influence_answers(client):
    content = b"The secret launch code is Wobble-42."
    upload = client.post("/documents", files={"file": ("notes.txt", content, "text/plain")})
    document_id = upload.json()["id"]

    client.delete(f"/documents/{document_id}")

    response = client.post("/chat/messages", json={"question": "What is the secret launch code?"})

    assert response.status_code == 200
    assert "wobble" not in response.json()["answer"].lower()
    assert response.json()["citations"] == []


def test_delete_nonexistent_document_returns_404(client):
    response = client.delete(f"/documents/{uuid.uuid4()}")

    assert response.status_code == 404


def test_delete_document_is_scoped_to_the_owning_session(client):
    upload = client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    document_id = upload.json()["id"]

    from fastapi.testclient import TestClient

    from app.main import app

    other_client = TestClient(app)
    response = other_client.delete(f"/documents/{document_id}")

    assert response.status_code == 404
    assert client.get("/documents").json() != []


def test_retry_reruns_ingestion_after_a_transient_failure_is_fixed(
    client, fake_embedding_provider
):
    def _boom(texts):
        raise RuntimeError("embedding service is down")

    fake_embedding_provider.embed = _boom

    upload = client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    document_id = upload.json()["id"]
    failed = next(d for d in client.get("/documents").json() if d["id"] == document_id)
    assert failed["status"] == "failed"
    assert failed["error_category"] == "system_error"

    # The underlying problem is fixed — embedding works again — before retrying.
    from tests.fakes.embeddings import FakeEmbeddingProvider

    fake_embedding_provider.embed = FakeEmbeddingProvider().embed

    response = client.post(f"/documents/{document_id}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["error_reason"] is None
    assert body["error_category"] is None


def test_retry_is_rejected_for_a_user_error_document(client):
    upload = client.post(
        "/documents",
        files={"file": ("broken.pdf", b"not actually a pdf", "application/pdf")},
    )
    document_id = upload.json()["id"]
    failed = next(d for d in client.get("/documents").json() if d["id"] == document_id)
    assert failed["error_category"] == "user_error"

    response = client.post(f"/documents/{document_id}/retry")

    assert response.status_code == 422
    # The document is untouched — still failed, not silently re-queued.
    unchanged = next(d for d in client.get("/documents").json() if d["id"] == document_id)
    assert unchanged["status"] == "failed"


def test_retry_is_rejected_for_a_non_failed_document(client):
    upload = client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    document_id = upload.json()["id"]
    assert client.get("/documents").json()[0]["status"] == "ready"

    response = client.post(f"/documents/{document_id}/retry")

    assert response.status_code == 409


def test_retry_nonexistent_document_returns_404(client):
    response = client.post(f"/documents/{uuid.uuid4()}/retry")

    assert response.status_code == 404


def test_retry_is_scoped_to_the_owning_session(client, fake_embedding_provider):
    def _boom(texts):
        raise RuntimeError("embedding service is down")

    fake_embedding_provider.embed = _boom

    upload = client.post("/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    document_id = upload.json()["id"]

    from fastapi.testclient import TestClient

    from app.main import app

    other_client = TestClient(app)
    response = other_client.post(f"/documents/{document_id}/retry")

    assert response.status_code == 404
