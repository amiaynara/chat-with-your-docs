import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.qa.answering import answer_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


@router.post("/messages", response_model=AskResponse)
def ask_question(request: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    try:
        answer = answer_question(db, request.question)
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
    return AskResponse(answer=answer)
