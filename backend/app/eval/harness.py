import enum
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import providers
from app.adapters.llm import Message
from app.config import settings
from app.eval.golden_set import GOLDEN_SET, GoldenItem
from app.eval.scoring import JUDGE_SYSTEM_PROMPT, JudgeScore, parse_judge_response, retrieval_hit
from app.ingestion.chunking import chunk_sections
from app.ingestion.spans import TextSpan
from app.models import Chunk, DocumentStatus
from app.qa.answering import answer_question
from app.repositories import ChunkRepository, DocumentRepository


class PipelineMode(enum.StrEnum):
    VECTOR_ONLY = "vector_only"
    VECTOR_PLUS_RERANK = "vector_plus_rerank"


@dataclass(frozen=True)
class ItemResult:
    question: str
    hit: bool
    judge: JudgeScore


@dataclass(frozen=True)
class ModeReport:
    mode: PipelineMode
    hit_rate: float
    avg_faithfulness: float
    avg_relevancy: float
    items: list[ItemResult] = field(default_factory=list)


@dataclass(frozen=True)
class EvalReport:
    vector_only: ModeReport
    vector_plus_rerank: ModeReport
    hit_rate_delta: float
    faithfulness_delta: float
    relevancy_delta: float


def seed_golden_documents(db: Session, session_id: str) -> None:
    """Ingest GOLDEN_SET's documents directly into READY chunks so
    answer_question can retrieve them, without going through object storage
    or Celery — this harness has no use for either (there's no uploaded
    file; the golden content is already in-process plaintext) — same
    parse->chunk->embed->store shape app.ingestion.tasks.ingest_document uses
    for a real upload, minus the parse/storage steps that don't apply here.

    One document per GoldenItem — GOLDEN_SET doesn't share a document across
    items (see its own docstring for why), so there's no per-filename dedup
    to do here.
    """
    embedder = providers.get_embedding_provider()
    documents = DocumentRepository(db)
    for item in GOLDEN_SET:
        document = documents.create(
            session_id=session_id,
            filename=item.document.filename,
            format=item.document.format,
            object_storage_key=f"eval/{item.document.filename}",
        )
        text_chunks = chunk_sections(
            [TextSpan(text=item.document.content, location_ref="document")],
            chunk_size=settings.chunk_size_chars,
            overlap_ratio=settings.chunk_overlap_ratio,
        )
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


def judge_answer(question: str, context: str, answer_text: str) -> JudgeScore:
    llm = providers.get_llm_provider()
    result = llm.generate(
        system=JUDGE_SYSTEM_PROMPT,
        messages=[
            Message(
                role="user",
                content=f"Question: {question}\nContext: {context}\nAnswer: {answer_text}",
            )
        ],
    )
    return parse_judge_response(result.text)


def _score_item(db: Session, session_id: str, item: GoldenItem) -> ItemResult:
    answer = answer_question(db, item.question, session_id=session_id)
    context = "\n\n".join(citation.snippet for citation in answer.citations)
    return ItemResult(
        question=item.question,
        hit=retrieval_hit(answer.citations, item.expected_passage),
        judge=judge_answer(item.question, context, answer.text),
    )


def _run_mode(
    db: Session, session_id: str, mode: PipelineMode, *, reranker_enabled: bool
) -> ModeReport:
    # settings.reranker_enabled is the same process-wide toggle answer_question
    # itself reads (app/config.py, issue #12) — flipped here and restored
    # unconditionally so a run through one mode never leaks into the other, or
    # into whatever this process's caller had it set to before/after.
    original = settings.reranker_enabled
    settings.reranker_enabled = reranker_enabled
    try:
        items = [_score_item(db, session_id, item) for item in GOLDEN_SET]
    finally:
        settings.reranker_enabled = original

    count = len(items)
    return ModeReport(
        mode=mode,
        hit_rate=sum(item.hit for item in items) / count,
        avg_faithfulness=sum(item.judge.faithfulness for item in items) / count,
        avg_relevancy=sum(item.judge.relevancy for item in items) / count,
        items=items,
    )


def compute_deltas(
    vector_only: ModeReport, vector_plus_rerank: ModeReport
) -> tuple[float, float, float]:
    """hit-rate/faithfulness/relevancy deltas, vector+rerank minus vector-only
    — positive means reranking measurably helped on that axis, negative means
    it measurably hurt. Split out from run_eval so the arithmetic itself is
    directly testable against fixture ModeReports, independent of whether a
    real run against the golden set happens to produce a nonzero difference.
    """
    return (
        vector_plus_rerank.hit_rate - vector_only.hit_rate,
        vector_plus_rerank.avg_faithfulness - vector_only.avg_faithfulness,
        vector_plus_rerank.avg_relevancy - vector_only.avg_relevancy,
    )


def run_eval(db: Session, session_id: str | None = None) -> EvalReport:
    """Run GOLDEN_SET through both the vector-only and vector+rerank pipeline
    modes (issue #12's toggle) and report hit-rate / faithfulness / relevancy
    for each, plus the rerank-vs-vector-only delta on all three — turning the
    reranker's contribution into a measured claim instead of an assumption.

    `session_id` scopes retrieval the same way it does for a real chat
    request (see answer_question) — defaults to a fresh id per call so a run
    never sees another run's (or another session's) documents.
    """
    session_id = session_id or f"eval-{uuid.uuid4()}"
    vector_only = _run_mode(db, session_id, PipelineMode.VECTOR_ONLY, reranker_enabled=False)
    vector_plus_rerank = _run_mode(
        db, session_id, PipelineMode.VECTOR_PLUS_RERANK, reranker_enabled=True
    )
    hit_rate_delta, faithfulness_delta, relevancy_delta = compute_deltas(
        vector_only, vector_plus_rerank
    )
    return EvalReport(
        vector_only=vector_only,
        vector_plus_rerank=vector_plus_rerank,
        hit_rate_delta=hit_rate_delta,
        faithfulness_delta=faithfulness_delta,
        relevancy_delta=relevancy_delta,
    )
