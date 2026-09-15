import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
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
    id: uuid.UUID
    filename: str
    format: DocumentFormat
    status: str
    error_reason: str | None
    error_category: DocumentErrorCategory | None
    created_at: datetime

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


@router.post("", response_model=DocumentOut, status_code=201)
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


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> list[DocumentOut]:
    documents = DocumentRepository(db).list_for_session(session_id)
    return [DocumentOut.model_validate(document) for document in documents]


@router.delete("/{document_id}", status_code=204)
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


@router.post("/{document_id}/retry", response_model=DocumentOut)
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
