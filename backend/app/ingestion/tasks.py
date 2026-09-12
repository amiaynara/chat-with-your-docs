import uuid

from app import providers
from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.ingestion.chunking import chunk_sections
from app.ingestion.parsing import DocumentParseError, parse_document
from app.models import Chunk, DocumentStatus
from app.repositories import ChunkRepository, DocumentRepository


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
            if not text_chunks:
                raise DocumentParseError("No content could be extracted from this document")

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
            documents.set_status(document.id, DocumentStatus.FAILED, error_reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - any adapter/infra failure surfaces to the user
            documents.set_status(
                document.id, DocumentStatus.FAILED, error_reason=f"Ingestion failed: {exc}"
            )
    finally:
        db.close()
