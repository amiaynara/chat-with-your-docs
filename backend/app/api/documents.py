import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import providers
from app.config import settings
from app.db import get_db
from app.ingestion.tasks import ingest_document
from app.models import DocumentFormat
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
