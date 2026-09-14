import uuid
from unittest.mock import patch

from app.db import SessionLocal
from app.ingestion.tasks import GENERIC_FAILURE_MESSAGE, ingest_document
from app.models import DocumentStatus
from app.repositories import DocumentRepository


def test_ingest_document_is_a_no_op_for_a_nonexistent_document_id():
    # Should return quietly rather than raise — a defensive guard against a
    # task racing a (future) delete, not something that can currently happen
    # via the API, but still cheap to keep correct.
    ingest_document(str(uuid.uuid4()))


def test_ingest_document_marks_failed_on_an_unexpected_embedding_error(
    fake_object_storage, fake_embedding_provider
):
    db = SessionLocal()
    try:
        storage_key = "session/doc.txt"
        fake_object_storage.put(storage_key, b"hello world")
        document = DocumentRepository(db).create(
            session_id="session",
            filename="doc.txt",
            format="txt",
            object_storage_key=storage_key,
        )
        document_id = document.id
    finally:
        db.close()

    def _boom(texts):
        raise RuntimeError("embedding service is down")

    fake_embedding_provider.embed = _boom

    with patch("app.ingestion.tasks.logger") as mock_logger:
        ingest_document(str(document_id))

        # The real exception and document context are captured for developers...
        mock_logger.exception.assert_called_once()
        logged_message, *logged_args = mock_logger.exception.call_args.args
        assert (logged_message % tuple(logged_args)) == (
            f"Ingestion failed for document_id={document_id} filename='doc.txt'"
        )

    # ...while the user only ever sees a sanitized, actionable message — never
    # the raw internal/infra exception text (which may leak config or provider
    # detail, e.g. a missing API key).
    db = SessionLocal()
    try:
        refreshed = DocumentRepository(db).get(document_id)
        assert refreshed.status == DocumentStatus.FAILED
        assert refreshed.error_reason == GENERIC_FAILURE_MESSAGE
    finally:
        db.close()
