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

    def delete(self, document: Document) -> None:
        # Chunk.document has cascade="all, delete-orphan" (app/models.py) and the FK
        # itself is ondelete="CASCADE", so deleting the Document row takes its chunks
        # (and their embeddings) with it — no separate chunk cleanup needed here.
        self._db.delete(document)
        self._db.commit()


class ChunkRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def bulk_create(self, chunks: list[Chunk]) -> None:
        self._db.add_all(chunks)
        self._db.commit()

    def search_ready(self, query_embedding: list[float], limit: int) -> list[tuple[Chunk, float]]:
        """Return the `limit` nearest READY chunks, each paired with its cosine
        distance to `query_embedding` — 0 means identical direction. (In general
        cosine distance ranges up to 2; neither real embedding model here — OpenAI's
        or the local sentence-transformers one — is guaranteed to produce
        non-negative-only vectors, so don't assume a 1.0 ceiling for real embeddings.
        Only the deterministic bag-of-words fake used in tests has that property,
        since it sums non-negative word counts.) Callers use the distance to judge
        whether a match is relevant at all, not just to rank matches against each
        other.
        """
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(Chunk, distance)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.status == DocumentStatus.READY)
            .order_by(distance)
            .limit(limit)
        )
        return [(chunk, dist) for chunk, dist in self._db.execute(stmt).all()]
