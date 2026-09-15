import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import providers
from app.config import settings
from app.db import get_db
from app.ingestion.tasks import ingest_document
from app.models import DocumentErrorCategory, DocumentFormat, DocumentStatus
from app.repositories import DocumentRepository
from app.session import get_session_id

router = APIRouter(prefix="/documents", tags=["documents"])

_EXTENSION_TO_FORMAT = {
    ".pdf": DocumentFormat.PDF,
    ".txt": DocumentFormat.TXT,
    ".md": DocumentFormat.MD,
}


class DocumentOut(BaseModel):
    """A document's ingestion record.

    `status` moves through the pipeline as `queued` → `processing` →
    `ready`, or `failed` if ingestion could not complete. `error_reason` and
    `error_category` are only ever set once `status` is `failed`; both are
    `null` otherwise.
    """

    id: uuid.UUID = Field(description="Unique identifier for the document.")
    filename: str = Field(description="Original filename as uploaded.")
    format: DocumentFormat = Field(
        description="Document format, inferred from the file extension at upload time."
    )
    status: str = Field(
        description="Position in the ingestion lifecycle: "
        "'queued', 'processing', 'ready', or 'failed'."
    )
    error_reason: str | None = Field(
        description="Human-readable explanation of the ingestion failure. "
        "Set only when status is 'failed'; null otherwise."
    )
    error_category: DocumentErrorCategory | None = Field(
        description="Set only when status is 'failed'. 'user_error' means the file itself is "
        "the problem (terminal — fix it and re-upload; POST .../retry is rejected). "
        "'system_error' means an infra/provider problem unrelated to the file (retryable via "
        "POST .../retry). Null unless status is 'failed'."
    )
    created_at: datetime = Field(description="When the document was uploaded.")

    model_config = {"from_attributes": True}


def _resolve_format(filename: str) -> DocumentFormat:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    document_format = _EXTENSION_TO_FORMAT.get(suffix)
    if document_format is None:
        allowed = ", ".join(settings.allowed_upload_extensions)
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{suffix or filename}'. Allowed types: {allowed}",
        )
    return document_format


@router.post(
    "",
    response_model=DocumentOut,
    status_code=201,
    summary="Upload a document for ingestion",
    description="Stores the uploaded file (pdf, txt, or md) in object storage and enqueues it "
    "for background ingestion (parse → chunk → embed → index). The returned document is "
    "'queued'; poll GET /documents to observe it move to 'processing' and then 'ready' or "
    "'failed'.",
    responses={
        422: {
            "description": "The upload is invalid: missing filename, an unsupported file "
            "extension, an empty file, or a file over the size limit."
        },
        502: {
            "description": "Object storage rejected the request "
            "(check credentials/configuration)."
        },
        503: {"description": "Object storage is temporarily unavailable. Try again shortly."},
    },
)
async def upload_document(
    file: UploadFile,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> DocumentOut:
    if not file.filename:
        raise HTTPException(status_code=422, detail="Uploaded file is missing a filename")

    document_format = _resolve_format(file.filename)

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        max_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=422, detail=f"File exceeds the {max_mb}MB size limit")
    if len(data) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    storage_key = f"{session_id}/{uuid.uuid4()}-{file.filename}"
    providers.get_object_storage().put(storage_key, data)

    document = DocumentRepository(db).create(
        session_id=session_id,
        filename=file.filename,
        format=document_format,
        object_storage_key=storage_key,
    )

    ingest_document.delay(str(document.id))

    return DocumentOut.model_validate(document)


@router.get(
    "",
    response_model=list[DocumentOut],
    summary="List the asking session's documents",
    description="Returns every document uploaded by the asking session (identified by its "
    "anonymous session cookie), newest first. Never includes another session's documents.",
)
def list_documents(
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> list[DocumentOut]:
    documents = DocumentRepository(db).list_for_session(session_id)
    return [DocumentOut.model_validate(document) for document in documents]


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Delete a document",
    description="Removes the document, its chunks/embeddings, and its object storage blob. "
    "Its chunks stop influencing future answers immediately.",
    responses={
        404: {
            "description": "No document with this id exists in the asking session's own "
            "document library (also returned for another session's document, to avoid "
            "confirming that the id belongs to someone else)."
        }
    },
)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> None:
    repo = DocumentRepository(db)
    document = repo.get(document_id)
    # A document that exists but belongs to another session reads as "not found"
    # rather than 403 — same scoping stance as list_documents, and avoids
    # confirming a document id belongs to someone else's session.
    if document is None or document.session_id != session_id:
        raise HTTPException(status_code=404, detail="Document not found")

    providers.get_object_storage().delete(document.object_storage_key)
    repo.delete(document)


@router.post(
    "/{document_id}/retry",
    response_model=DocumentOut,
    summary="Retry a failed document's ingestion",
    description="Re-enqueues ingestion for a 'failed' document using its existing stored "
    "object-storage blob — no re-upload required. Only allowed when the failure was "
    "classified 'system_error' (an infra/provider problem, not the file itself).",
    responses={
        404: {
            "description": "No document with this id exists in the asking session's own "
            "document library (also returned for another session's document, to avoid "
            "confirming that the id belongs to someone else)."
        },
        409: {
            "description": "The document isn't 'failed' — only a failed document can be retried."
        },
        422: {
            "description": "The document's failure is a 'user_error' (a problem with the file "
            "itself, e.g. a corrupt PDF) — not retryable. Fix the file and re-upload instead."
        },
    },
)
def retry_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> DocumentOut:
    repo = DocumentRepository(db)
    document = repo.get(document_id)
    if document is None or document.session_id != session_id:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != DocumentStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only a failed document can be retried")
    if document.error_category == DocumentErrorCategory.USER_ERROR:
        raise HTTPException(
            status_code=422,
            detail="This document failed because of the file itself — fix it and re-upload "
            "instead of retrying",
        )

    repo.set_status(document.id, DocumentStatus.QUEUED)
    ingest_document.delay(str(document.id))

    db.refresh(document)
    return DocumentOut.model_validate(document)
