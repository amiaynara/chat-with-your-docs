import uuid

from app.db import SessionLocal
from app.models import DocumentStatus, MessageRole
from app.repositories import DocumentRepository, MessageRepository


def test_set_status_is_a_no_op_for_a_nonexistent_document():
    db = SessionLocal()
    try:
        # Should not raise even though no document with this id exists.
        DocumentRepository(db).set_status(uuid.uuid4(), DocumentStatus.FAILED, "irrelevant")
    finally:
        db.close()


def test_delete_for_session_removes_only_that_sessions_messages():
    db = SessionLocal()
    try:
        repo = MessageRepository(db)
        session_id = str(uuid.uuid4())
        other_session_id = str(uuid.uuid4())
        repo.create(session_id=session_id, role=MessageRole.USER, content="mine")
        repo.create(session_id=other_session_id, role=MessageRole.USER, content="not mine")

        repo.delete_for_session(session_id)

        assert repo.list_for_session(session_id) == []
        assert len(repo.list_for_session(other_session_id)) == 1
    finally:
        db.close()
