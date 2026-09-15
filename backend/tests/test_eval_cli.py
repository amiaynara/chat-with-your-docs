"""Tests for the runnable `python -m app.eval` entry point (issue #13)."""

from sqlalchemy import select

from app.db import SessionLocal
from app.eval import __main__ as eval_cli
from app.eval.__main__ import main
from app.models import Document


def test_main_prints_a_report_and_cleans_up_its_seeded_documents(
    capsys, fake_embedding_provider, fake_llm_provider, fake_reranker_provider
):
    report = main()

    out = capsys.readouterr().out
    assert "vector_only" in out
    assert "vector_plus_rerank" in out
    assert "delta" in out
    assert report.vector_only.hit_rate == 1.0

    db = SessionLocal()
    try:
        assert db.scalars(select(Document)).all() == []
    finally:
        db.close()


def test_main_cleans_up_even_when_run_eval_raises(
    monkeypatch, fake_embedding_provider, fake_llm_provider
):
    def _boom(db, session_id=None):
        raise RuntimeError("judge provider unavailable")

    monkeypatch.setattr(eval_cli, "run_eval", _boom)

    try:
        main()
    except RuntimeError:
        pass

    db = SessionLocal()
    try:
        assert db.scalars(select(Document)).all() == []
    finally:
        db.close()
