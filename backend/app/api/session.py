from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import providers
from app.config import settings
from app.db import get_db
from app.repositories import DocumentRepository, MessageRepository
from app.session import get_session_id

router = APIRouter(prefix="/session", tags=["session"])


@router.post(
    "/reset",
    status_code=204,
    summary="End the current session",
    description="Deletes every document (object storage blob + chunks) and chat message "
    "belonging to the asking session, then clears the session cookie. The next request "
    "starts a brand-new, empty session — there is no way to undo this.",
)
def reset_session(
    response: Response,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> None:
    document_repo = DocumentRepository(db)
    object_storage = providers.get_object_storage()
    for document in document_repo.list_for_session(session_id):
        object_storage.delete(document.object_storage_key)
        document_repo.delete(document)

    MessageRepository(db).delete_for_session(session_id)

    response.delete_cookie(settings.session_cookie_name)
