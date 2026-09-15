import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentStatus, Message, MessageRole


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

    def search_ready(
        self,
        query_embedding: list[float],
        limit: int,
        session_id: str,
        doc_ids: list[uuid.UUID] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Return the `limit` nearest READY chunks, each paired with its cosine
        distance to `query_embedding` — 0 means identical direction. (In general
        cosine distance ranges up to 2; neither real embedding model here — OpenAI's
        or the local sentence-transformers one — is guaranteed to produce
        non-negative-only vectors, so don't assume a 1.0 ceiling for real embeddings.
        Only the deterministic bag-of-words fake used in tests has that property,
        since it sums non-negative word counts.) Callers use the distance to judge
        whether a match is relevant at all, not just to rank matches against each
        other.

        `session_id` restricts the candidate set to the asking session's own
        documents — applied in the WHERE clause before ORDER BY/LIMIT, same as
        `doc_ids` below. The session cookie is this app's only privacy boundary
        (no accounts), so this is not optional the way `doc_ids` is (issue #20).

        `doc_ids`, if given (non-empty), further restricts the (already
        session-scoped) candidate set to those documents' chunks *inside this
        same query* — applied in the WHERE clause before ORDER BY/LIMIT, not as
        a filter over an already-fetched unscoped top-`limit` result. That
        distinction matters: post-filtering an unscoped top-k could silently
        return fewer than `limit` relevant scoped chunks (or none at all)
        whenever other documents' chunks are more similar to the query and
        crowd the scoped ones out of that top-k window.
        """
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(Chunk, distance)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.status == DocumentStatus.READY, Document.session_id == session_id)
        )
        if doc_ids:
            stmt = stmt.where(Chunk.document_id.in_(doc_ids))
        stmt = stmt.order_by(distance).limit(limit)
        return [(chunk, dist) for chunk, dist in self._db.execute(stmt).all()]


class MessageRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_session(self, session_id: str) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        return list(self._db.scalars(stmt).all())

    def create(
        self,
        *,
        session_id: str,
        role: MessageRole,
        content: str,
        citations: list[dict] | None = None,
    ) -> Message:
        message = Message(session_id=session_id, role=role, content=content, citations=citations)
        self._db.add(message)
        self._db.commit()
        self._db.refresh(message)
        return message
