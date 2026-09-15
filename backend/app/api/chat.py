import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.llm import Message as LLMMessage
from app.config import settings
from app.db import get_db
from app.models import MessageRole
from app.qa.answering import Answer, Citation, RerankScore, RetrievalHit, Trace, answer_question
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


class StageTimingOut(BaseModel):
    stage: str = Field(description="Pipeline stage name: 'embed_query', 'retrieve', 'rerank' "
        "(only when reranking is enabled), or 'generate'.")
    duration_ms: float = Field(description="How long this stage took, in milliseconds.")


class RetrievalHitOut(BaseModel):
    """One candidate chunk retrieval turned up, before the relevance filter."""

    document_id: uuid.UUID = Field(description="Id of the document this chunk is from.")
    filename: str = Field(description="Filename of the document this chunk is from.")
    location_ref: str = Field(description="Human-readable location within the document.")
    distance: float = Field(description="Cosine distance to the query embedding (lower = closer).")
    keyword_match: bool = Field(
        description="Whether this chunk also matched the full-text keyword search branch."
    )
    included: bool = Field(
        description="Whether this hit cleared the relevance filter and was actually used "
        "(passed to reranking, if enabled, and placed in the prompt)."
    )

    @classmethod
    def from_hit(cls, hit: RetrievalHit) -> "RetrievalHitOut":
        return cls(
            document_id=hit.document_id,
            filename=hit.filename,
            location_ref=hit.location_ref,
            distance=hit.distance,
            keyword_match=hit.keyword_match,
            included=hit.included,
        )


class RerankScoreOut(BaseModel):
    document_id: uuid.UUID = Field(description="Id of the reranked chunk's document.")
    location_ref: str = Field(description="Human-readable location within the document.")
    relevance_score: float = Field(description="Relevance score assigned by the reranker.")

    @classmethod
    def from_score(cls, score: RerankScore) -> "RerankScoreOut":
        return cls(
            document_id=score.document_id,
            location_ref=score.location_ref,
            relevance_score=score.relevance_score,
        )


class TraceOut(BaseModel):
    """Diagnostic detail behind an answer — the "inspect this answer" panel's
    data (issue #14): what retrieval actually found, how (if at all) reranking
    reordered it, the exact prompt sent to the LLM, token usage, and per-stage
    latency.
    """

    retrieval_hits: list[RetrievalHitOut] = Field(
        description="Every candidate chunk retrieval turned up, before the relevance filter."
    )
    rerank_scores: list[RerankScoreOut] | None = Field(
        description="Reranker output, in relevance order. Null when reranking wasn't used "
        "for this answer (RERANKER_ENABLED is off, or no relevant chunks were found)."
    )
    prompt: str | None = Field(
        description="The exact system prompt (including the assembled <context> block) sent "
        "to the LLM. Null when the LLM was never called (no relevant chunks were found)."
    )
    input_tokens: int = Field(description="Input tokens billed for the LLM call. 0 if not called.")
    output_tokens: int = Field(
        description="Output tokens billed for the LLM call. 0 if not called."
    )
    stage_timings: list[StageTimingOut] = Field(
        description="How long each pipeline stage that actually ran took, in order."
    )

    @classmethod
    def from_trace(cls, trace: Trace) -> "TraceOut":
        return cls(
            retrieval_hits=[RetrievalHitOut.from_hit(hit) for hit in trace.retrieval_hits],
            rerank_scores=[RerankScoreOut.from_score(s) for s in trace.rerank_scores]
            if trace.rerank_scores is not None
            else None,
            prompt=trace.prompt,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            stage_timings=[
                StageTimingOut(stage=t.stage, duration_ms=t.duration_ms)
                for t in trace.stage_timings
            ],
        )


class AskResponse(BaseModel):
    answer: str = Field(description="The generated answer text.")
    citations: list[CitationOut] = Field(
        description="Sources the answer draws on. Empty when no relevant evidence was found "
        "(the model was instructed to refuse rather than guess) or when the session has no "
        "documents yet."
    )
    trace: TraceOut = Field(
        description="Diagnostic detail behind this answer, for the 'inspect this answer' panel."
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
        return AskResponse(
            answer=_NO_DOCUMENTS_MESSAGE, citations=[], trace=TraceOut.from_trace(Trace())
        )

    result = _generate_answer_or_502(db, request.question, session_id, request.doc_ids, history)
    citations_out = [CitationOut.from_citation(c) for c in result.citations]

    message_repo.create(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=result.text,
        citations=[c.model_dump(mode="json") for c in citations_out] or None,
    )

    return AskResponse(
        answer=result.text, citations=citations_out, trace=TraceOut.from_trace(result.trace)
    )


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
