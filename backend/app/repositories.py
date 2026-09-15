import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentStatus, Message, MessageRole


@dataclass
class ScoredChunk:
    """One candidate returned by ChunkRepository.search_ready.

    `distance` is always the real cosine distance to the query embedding
    (see search_ready's docstring for its scale), computed regardless of
    which branch — vector or keyword — actually surfaced this chunk.
    `keyword_match` is True when the chunk also matched the Postgres
    full-text search branch, independent of how far it is by vector
    distance — see search_ready for why that matters to callers.
    """

    chunk: Chunk
    distance: float
    keyword_match: bool


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
        query_text: str,
        limit: int,
        session_id: str,
        doc_ids: list[uuid.UUID] | None = None,
    ) -> list[ScoredChunk]:
        """Return up to `limit` scored READY chunks total: the nearest-by-vector
        candidates (up to `limit`) unioned with the best-by-keyword candidates (up
        to `limit`) — issue #11's hybrid retrieval — deduplicated and then itself
        capped back down to `limit`, keyword matches first. That final cap matters:
        each branch is independently allowed up to `limit` candidates, so their raw
        union can hold up to 2x `limit` distinct chunks; without re-capping it,
        `limit` would stop being an effective bound on how many chunks a caller ever
        sees, silently growing prompt size on a query that hits both branches hard.
        Keyword matches are kept ahead of vector-only candidates when the cap has to
        drop something, since (per below) a keyword match is unconditionally
        relevant while a vector-only candidate might not even clear the caller's own
        distance threshold — dropping the *guaranteed*-relevant one to keep a
        maybe-relevant one would defeat the point of hybrid retrieval.

        Each ScoredChunk carries its cosine distance to `query_embedding`
        — 0 means identical direction. (In general cosine distance ranges up to 2;
        neither real embedding model here — OpenAI's or the local
        sentence-transformers one — is guaranteed to produce non-negative-only
        vectors, so don't assume a 1.0 ceiling for real embeddings. Only the
        deterministic bag-of-words fake used in tests has that property, since it
        sums non-negative word counts.) Callers use the distance to judge whether a
        vector match is relevant at all, not just to rank matches against each
        other — but a chunk with `keyword_match=True` should be treated as
        relevant regardless of its distance: it's exactly the case a term the
        embedding didn't line up (a different word form/inflection Postgres's
        text-search config stems the same way the fake test embedding can't, or a
        rare term the real embedding model didn't weight highly) but a plain
        keyword search still finds outright.

        The keyword branch matches when the chunk's content shares *any*
        significant word (lexeme, after Postgres's English stemming) with
        `query_text` — an OR across the question's own lexemes, not a strict AND
        of the whole question the way websearch_to_tsquery's default parsing
        would require, since a real question is mostly function words
        ("how", "is", "the") a document restating the same fact in different
        words has no reason to also contain.

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
        content_tsv = func.to_tsvector("english", Chunk.content)
        # Build an OR-tsquery from the question's own lexemes — see the docstring
        # above for why (a strict-AND parse of the raw question, e.g. via
        # websearch_to_tsquery, would rarely match anything). An empty/all-stopword
        # `query_text` yields an empty tsquery, which safely matches nothing rather
        # than erroring.
        question_lexemes = func.array_to_string(
            func.tsvector_to_array(func.to_tsvector("english", query_text)), " | "
        )
        tsquery = func.to_tsquery("english", question_lexemes)
        keyword_match = content_tsv.op("@@")(tsquery).label("keyword_match")

        base = (
            select(Chunk, distance, keyword_match)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.status == DocumentStatus.READY, Document.session_id == session_id)
        )
        if doc_ids:
            base = base.where(Chunk.document_id.in_(doc_ids))

        vector_stmt = base.order_by(distance).limit(limit)
        keyword_stmt = (
            base.where(keyword_match)
            .order_by(func.ts_rank_cd(content_tsv, tsquery).desc())
            .limit(limit)
        )

        # `is_match` is computed by the same expression in both statements, so it's
        # intrinsic to the chunk regardless of which statement returned it — a
        # first-seen-wins merge is enough, no need to reconcile/update it on a
        # second sighting.
        merged: dict[uuid.UUID, ScoredChunk] = {}
        for chunk, dist, is_match in (
            *self._db.execute(vector_stmt).all(),
            *self._db.execute(keyword_stmt).all(),
        ):
            if chunk.id not in merged:
                merged[chunk.id] = ScoredChunk(chunk=chunk, distance=dist, keyword_match=is_match)

        ranked = sorted(
            merged.values(), key=lambda scored: (not scored.keyword_match, scored.distance)
        )
        return ranked[:limit]


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
