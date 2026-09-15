"""Runnable evaluation harness (issue #13).

    cd backend && uv run python -m app.eval

Seeds the golden document set (app/eval/golden_set.py) into a throwaway
session, runs it through both pipeline modes, prints a report, then deletes
what it seeded — this run's documents/chunks are never left behind in
whatever database DATABASE_URL points at.

Uses the same provider configuration as the running app (settings.*, see
app/config.py): vector+rerank mode needs RERANKER_ENABLED-capable config
(COHERE_API_KEY) the same way a real chat request would.
"""

import uuid

from app.db import SessionLocal
from app.eval.harness import EvalReport, ModeReport, run_eval, seed_golden_documents
from app.repositories import DocumentRepository


def _print_mode(report: ModeReport) -> None:
    print(f"\n  {report.mode}")
    print(f"    hit-rate:     {report.hit_rate:.2f}")
    print(f"    faithfulness: {report.avg_faithfulness:.2f}")
    print(f"    relevancy:    {report.avg_relevancy:.2f}")
    for item in report.items:
        print(
            f"      [{'HIT' if item.hit else 'MISS'}] "
            f"faithfulness={item.judge.faithfulness:.2f} "
            f"relevancy={item.judge.relevancy:.2f} — {item.question}"
        )


def _print_report(report: EvalReport) -> None:
    print("Evaluation harness report")
    print("=" * 40)
    _print_mode(report.vector_only)
    _print_mode(report.vector_plus_rerank)
    print("\n  vector+rerank vs vector-only delta")
    print(f"    hit-rate:     {report.hit_rate_delta:+.2f}")
    print(f"    faithfulness: {report.faithfulness_delta:+.2f}")
    print(f"    relevancy:    {report.relevancy_delta:+.2f}")


def main() -> EvalReport:
    session_id = f"eval-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        seed_golden_documents(db, session_id)
        report = run_eval(db, session_id)
        _print_report(report)
        return report
    finally:
        documents = DocumentRepository(db)
        for document in documents.list_for_session(session_id):
            documents.delete(document)
        db.close()


if __name__ == "__main__":  # pragma: no cover - exercised via `python -m app.eval`, not pytest
    main()
