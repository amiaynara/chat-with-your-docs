import logging
import uuid

from app import providers
from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.ingestion.chunking import chunk_sections
from app.ingestion.parsing import DocumentParseError, parse_document
from app.models import Chunk, DocumentErrorCategory, DocumentStatus
from app.repositories import ChunkRepository, DocumentRepository

logger = logging.getLogger(__name__)

# Shown to the user in place of the raw exception, which may be an internal
# infra/config error (e.g. a missing provider API key) that isn't theirs to
# fix and shouldn't leak implementation detail. The real exception still goes
# to the logs via logger.exception below.
GENERIC_FAILURE_MESSAGE = (
    "We couldn't process this document due to a system error on our end. "
    "Please try uploading again, or contact support if this keeps happening."
)


@celery_app.task(name="app.ingestion.tasks.ingest_document")
def ingest_document(document_id: str) -> None:
    db = SessionLocal()
    try:
        documents = DocumentRepository(db)
        document = documents.get(uuid.UUID(document_id))
        if document is None:
            return

        documents.set_status(document.id, DocumentStatus.PROCESSING)

        try:
            storage = providers.get_object_storage()
            data = storage.get(document.object_storage_key)

            sections = parse_document(data, document.format)
            text_chunks = chunk_sections(
                sections,
                chunk_size=settings.chunk_size_chars,
                overlap_ratio=settings.chunk_overlap_ratio,
            )

            embedder = providers.get_embedding_provider()
            vectors = embedder.embed([chunk.text for chunk in text_chunks])

            chunk_rows = [
                Chunk(
                    document_id=document.id,
                    content=chunk.text,
                    location_ref=chunk.location_ref,
                    embedding=vector,
                    embedding_model=embedder.model_name,
                    embedding_version=embedder.model_version,
                )
                for chunk, vector in zip(text_chunks, vectors, strict=True)
            ]
            ChunkRepository(db).bulk_create(chunk_rows)

            documents.set_status(document.id, DocumentStatus.READY)
        except DocumentParseError as exc:
            logger.warning(
                "Document parse failed for document_id=%s filename=%r: %s",
                document.id,
                document.filename,
                exc,
            )
            documents.set_status(
                document.id,
                DocumentStatus.FAILED,
                error_reason=str(exc),
                error_category=DocumentErrorCategory.USER_ERROR,
            )
        except Exception:  # noqa: BLE001 - any adapter/infra failure; logged in full, sanitized for the user
            logger.exception(
                "Ingestion failed for document_id=%s filename=%r",
                document.id,
                document.filename,
            )
            documents.set_status(
                document.id,
                DocumentStatus.FAILED,
                error_reason=GENERIC_FAILURE_MESSAGE,
                error_category=DocumentErrorCategory.SYSTEM_ERROR,
            )
    finally:
        db.close()
