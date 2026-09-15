"""Tests for the eval harness's orchestration (issue #13) — runs the real
seed -> answer_question -> judge pipeline against the fake providers, the
same fakes the rest of the suite uses in place of live services.
"""

from app.config import settings
from app.db import SessionLocal
from app.eval.golden_set import GOLDEN_SET
from app.eval.harness import (
    ModeReport,
    PipelineMode,
    compute_deltas,
    judge_answer,
    run_eval,
    seed_golden_documents,
)
from app.qa.answering import answer_question


def test_run_eval_reports_both_pipeline_modes_and_their_delta(
    fake_embedding_provider, fake_llm_provider, fake_reranker_provider
):
    db = SessionLocal()
    try:
        seed_golden_documents(db, "eval-session")
        report = run_eval(db, "eval-session")
    finally:
        db.close()

    assert report.vector_only.mode == PipelineMode.VECTOR_ONLY
    assert report.vector_plus_rerank.mode == PipelineMode.VECTOR_PLUS_RERANK
    assert [item.question for item in report.vector_only.items] == [
        item.question for item in GOLDEN_SET
    ]
    assert len(report.vector_plus_rerank.items) == len(GOLDEN_SET)

    # Every golden question is answerable from its own small, single-chunk
    # document — issue #11's hybrid retrieval (keyword branch) finds it via
    # shared/stemmed vocabulary regardless of the fake embedding's coarser
    # match, in both pipeline modes.
    assert report.vector_only.hit_rate == 1.0
    assert report.vector_plus_rerank.hit_rate == 1.0
    assert report.hit_rate_delta == 0.0

    for mode_report in (report.vector_only, report.vector_plus_rerank):
        assert 0.0 <= mode_report.avg_faithfulness <= 1.0
        assert 0.0 <= mode_report.avg_relevancy <= 1.0

    assert report.faithfulness_delta == (
        report.vector_plus_rerank.avg_faithfulness - report.vector_only.avg_faithfulness
    )
    assert report.relevancy_delta == (
        report.vector_plus_rerank.avg_relevancy - report.vector_only.avg_relevancy
    )


def test_compute_deltas_is_vector_plus_rerank_minus_vector_only():
    # Fixture ModeReports with deliberately differing (including a negative)
    # values on all three axes — proves the delta arithmetic itself, rather
    # than relying on a real golden-set run happening to diverge between
    # modes (see test_run_eval_reports_both_pipeline_modes_and_their_delta,
    # where it doesn't).
    vector_only = ModeReport(
        mode=PipelineMode.VECTOR_ONLY, hit_rate=0.5, avg_faithfulness=0.4, avg_relevancy=0.9
    )
    vector_plus_rerank = ModeReport(
        mode=PipelineMode.VECTOR_PLUS_RERANK,
        hit_rate=0.75,
        avg_faithfulness=0.9,
        avg_relevancy=0.5,
    )

    hit_rate_delta, faithfulness_delta, relevancy_delta = compute_deltas(
        vector_only, vector_plus_rerank
    )

    assert hit_rate_delta == 0.25
    assert faithfulness_delta == 0.5
    assert relevancy_delta == -0.4


def test_judge_answer_scores_a_grounded_on_topic_answer_higher_than_a_hallucinated_one(
    fake_llm_provider,
):
    question = "What is the office Wi-Fi password?"
    context = "The office Wi-Fi password is Sunshine123, updated monthly by IT."

    # A "known-good" answer: on-topic and drawn entirely from the context.
    good = judge_answer(
        question, context, answer_text="The office Wi-Fi password is Sunshine123."
    )
    # A "known-bad" answer: on neither the question's topic nor supported by
    # the context — a stand-in for a hallucinated/off-topic real answer.
    bad = judge_answer(
        question, context, answer_text="The office is located in Berlin and employs 500 people."
    )

    assert good.faithfulness > bad.faithfulness
    assert good.relevancy > bad.relevancy


def test_run_eval_leaves_the_reranker_toggle_as_it_found_it(
    fake_embedding_provider, fake_llm_provider, fake_reranker_provider
):
    original = settings.reranker_enabled
    db = SessionLocal()
    try:
        seed_golden_documents(db, "eval-session")
        run_eval(db, "eval-session")
    finally:
        db.close()

    assert settings.reranker_enabled == original


def test_run_eval_defaults_to_a_fresh_session_id_per_call(
    fake_embedding_provider, fake_llm_provider
):
    # No session_id given, and no documents seeded — a real run always seeds
    # under the session it evaluates, so this just proves a bare call doesn't
    # blow up or silently reuse some other run's/global state.
    db = SessionLocal()
    try:
        report = run_eval(db)
    finally:
        db.close()

    assert report.vector_only.hit_rate == 0.0


def test_golden_set_is_answerable_from_its_own_seeded_documents(
    fake_embedding_provider, fake_llm_provider
):
    db = SessionLocal()
    try:
        seed_golden_documents(db, "eval-session")
        for item in GOLDEN_SET:
            answer = answer_question(db, item.question, session_id="eval-session")
            assert item.expected_answer_contains.lower() in answer.text.lower()
    finally:
        db.close()
