import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.llm import Message as LLMMessage
from app.config import settings
from app.db import get_db
from app.models import MessageRole
from app.qa.answering import Citation, answer_question
from app.repositories import DocumentRepository, MessageRepository
from app.session import get_session_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Shown instead of attempting to answer when the session's document library is
# empty — distinct from answer_question's generic no-evidence refusal, which
# covers "documents exist but none are relevant" rather than "there's nothing
# to search at all".
_NO_DOCUMENTS_MESSAGE = (
    "You haven't uploaded any documents yet — upload a PDF, txt, or Markdown file "
    "before asking a question."
)


class AskRequest(BaseModel):
    question: str
    doc_ids: list[uuid.UUID] | None = None


class CitationOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    location_ref: str
    snippet: str


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]


class MessageOut(BaseModel):
    role: str
    content: str
    citations: list[CitationOut] | None = None


def _citation_to_dict(citation: Citation) -> dict:
    # UUID isn't JSON-serializable as-is; stored as str, read back into a UUID
    # field by CitationOut's own validation when replayed via GET /chat/messages.
    return {
        "document_id": str(citation.document_id),
        "filename": citation.filename,
        "location_ref": citation.location_ref,
        "snippet": citation.snippet,
    }


@router.post("/messages", response_model=AskResponse)
def ask_question(
    request: AskRequest,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AskResponse:
    message_repo = MessageRepository(db)

    # Loaded before persisting the current question, so it never includes
    # itself — only turns from *before* this exchange.
    history_rows = message_repo.list_for_session(session_id)[-settings.chat_history_max_messages :]
    history = [LLMMessage(role=row.role.value, content=row.content) for row in history_rows]

    message_repo.create(session_id=session_id, role=MessageRole.USER, content=request.question)

    if not DocumentRepository(db).list_for_session(session_id):
        message_repo.create(
            session_id=session_id, role=MessageRole.ASSISTANT, content=_NO_DOCUMENTS_MESSAGE
        )
        return AskResponse(answer=_NO_DOCUMENTS_MESSAGE, citations=[])

    try:
        result = answer_question(db, request.question, doc_ids=request.doc_ids, history=history)
    except Exception:
        # Provider SDKs raise their own, inconsistent exception types for
        # configuration errors (e.g. a missing API key) that never reach our
        # adapters' classified Transient/PermanentProviderError handling —
        # surface a clean error instead of a bare 500. The raw exception is
        # logged, not returned to the client, to avoid leaking internals.
        logger.exception("Failed to answer question")
        raise HTTPException(
            status_code=502, detail="Could not get an answer right now. Please try again shortly."
        ) from None

    message_repo.create(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=result.text,
        citations=[_citation_to_dict(c) for c in result.citations] or None,
    )

    return AskResponse(
        answer=result.text,
        citations=[
            CitationOut(
                document_id=c.document_id,
                filename=c.filename,
                location_ref=c.location_ref,
                snippet=c.snippet,
            )
            for c in result.citations
        ],
    )


@router.get("/messages", response_model=list[MessageOut])
def get_message_history(
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> list[MessageOut]:
    messages = MessageRepository(db).list_for_session(session_id)
    return [
        MessageOut(
            role=message.role.value,
            content=message.content,
            citations=[CitationOut(**c) for c in message.citations]
            if message.citations
            else None,
        )
        for message in messages
    ]
