import pytest

from app import config
from app.adapters.retry import PermanentProviderError, TransientProviderError


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
