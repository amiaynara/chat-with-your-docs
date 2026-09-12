import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentStatus


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self, *, session_id: str, filename: str, format: str, object_storage_key: str
    ) -> Document:
        document = Document(
            session_id=session_id,
            filename=filename,
            format=format,
            object_storage_key=object_storage_key,
            status=DocumentStatus.QUEUED,
        )
        self._db.add(document)
        self._db.commit()
        self._db.refresh(document)
        return document

    def get(self, document_id: uuid.UUID) -> Document | None:
        return self._db.get(Document, document_id)

    def list_for_session(self, session_id: str) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.session_id == session_id)
            .order_by(Document.created_at.desc())
        )
        return list(self._db.scalars(stmt).all())

    def set_status(
        self, document_id: uuid.UUID, status: DocumentStatus, error_reason: str | None = None
    ) -> None:
        document = self.get(document_id)
        if document is None:
            return
        document.status = status
        document.error_reason = error_reason
        self._db.commit()


class ChunkRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def bulk_create(self, chunks: list[Chunk]) -> None:
        self._db.add_all(chunks)
        self._db.commit()

    def search_ready(
        self, query_embedding: list[float], limit: int, document_ids: list[uuid.UUID] | None = None
    ) -> list[Chunk]:
        stmt = (
            select(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.status == DocumentStatus.READY)
        )
        if document_ids:
            stmt = stmt.where(Document.id.in_(document_ids))
        stmt = stmt.order_by(Chunk.embedding.cosine_distance(query_embedding)).limit(limit)
        return list(self._db.scalars(stmt).all())
