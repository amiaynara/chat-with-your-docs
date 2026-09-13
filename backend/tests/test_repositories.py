import uuid

from app.db import SessionLocal
from app.models import DocumentStatus
from app.repositories import DocumentRepository


def test_set_status_is_a_no_op_for_a_nonexistent_document():
    db = SessionLocal()
    try:
        # Should not raise even though no document with this id exists.
        DocumentRepository(db).set_status(uuid.uuid4(), DocumentStatus.FAILED, "irrelevant")
    finally:
        db.close()
