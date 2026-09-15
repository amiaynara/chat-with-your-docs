import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.llm import Message as LLMMessage
from app.config import settings
from app.db import get_db
from app.models import MessageRole
from app.qa.answering import Answer, Citation, answer_question
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
    question: str = Field(description="The question to ask over the session's documents.")
    doc_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Restrict retrieval to these document ids (must belong to the asking "
        "session). Omit or leave null to search the whole session library.",
    )


class CitationOut(BaseModel):
    """A supporting source for part of an answer, pointing back at the chunk it came from."""

    document_id: uuid.UUID = Field(description="Id of the document this citation is from.")
    filename: str = Field(description="Filename of the cited document.")
    location_ref: str = Field(
        description="Human-readable location within the document, e.g. 'page 3'."
    )
    snippet: str = Field(description="The cited chunk's text, or an excerpt of it.")

    @classmethod
    def from_citation(cls, citation: Citation) -> "CitationOut":
        return cls(
            document_id=citation.document_id,
            filename=citation.filename,
            location_ref=citation.location_ref,
            snippet=citation.snippet,
        )


class AskResponse(BaseModel):
    answer: str = Field(description="The generated answer text.")
    citations: list[CitationOut] = Field(
        description="Sources the answer draws on. Empty when no relevant evidence was found "
        "(the model was instructed to refuse rather than guess) or when the session has no "
        "documents yet."
    )


class MessageOut(BaseModel):
    """One turn of the session's chat transcript."""

    role: str = Field(description="Who sent this turn: 'user' or 'assistant'.")
    content: str = Field(description="The turn's text — the question or the generated answer.")
    citations: list[CitationOut] | None = Field(
        default=None,
        description="Present only on an assistant turn that had supporting citations; "
        "null for a user turn or an assistant turn with none.",
    )


def _recent_history(message_repo: MessageRepository, session_id: str) -> list[LLMMessage]:
    """The session's recent turns from *before* this exchange (it hasn't been
    persisted yet when this is called), bounded to
    settings.chat_history_max_messages and converted to the shape
    answer_question expects for the LLM prompt.
    """
    rows = message_repo.list_for_session(session_id)[-settings.chat_history_max_messages :]
    return [LLMMessage(role=row.role.value, content=row.content) for row in rows]


def _generate_answer_or_502(
    db: Session,
    question: str,
    session_id: str,
    doc_ids: list[uuid.UUID] | None,
    history: list[LLMMessage],
) -> Answer:
    try:
        return answer_question(
            db, question, session_id=session_id, doc_ids=doc_ids, history=history
        )
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


@router.post(
    "/messages",
    response_model=AskResponse,
    summary="Ask a question over the session's documents",
    description="Retrieves relevant chunks (hybrid vector + keyword search, optionally "
    "reranked), generates a cited answer, and persists both the question and the answer to "
    "the session's chat history. Answers 'you haven't uploaded any documents yet' without "
    "calling the LLM if the session's document library is empty.",
    responses={
        502: {
            "description": "Could not get an answer from the LLM right now. Please try again "
            "shortly."
        }
    },
)
def ask_question(
    request: AskRequest,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AskResponse:
    message_repo = MessageRepository(db)
    history = _recent_history(message_repo, session_id)

    message_repo.create(session_id=session_id, role=MessageRole.USER, content=request.question)

    if not DocumentRepository(db).list_for_session(session_id):
        message_repo.create(
            session_id=session_id, role=MessageRole.ASSISTANT, content=_NO_DOCUMENTS_MESSAGE
        )
        return AskResponse(answer=_NO_DOCUMENTS_MESSAGE, citations=[])

    result = _generate_answer_or_502(db, request.question, session_id, request.doc_ids, history)
    citations_out = [CitationOut.from_citation(c) for c in result.citations]

    message_repo.create(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=result.text,
        citations=[c.model_dump(mode="json") for c in citations_out] or None,
    )

    return AskResponse(answer=result.text, citations=citations_out)


@router.get(
    "/messages",
    response_model=list[MessageOut],
    summary="Get the asking session's chat history",
    description="Returns every question/answer turn for the asking session (identified by its "
    "anonymous session cookie), oldest first.",
)
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
