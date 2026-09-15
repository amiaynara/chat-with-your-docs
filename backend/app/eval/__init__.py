"""Evaluation harness (issue #13): measures retrieval and answer quality
against a small golden Q&A set, and quantifies the reranker's contribution
(vector-only vs vector+rerank) rather than leaving it an unmeasured claim.

Run via `python -m app.eval` (see __main__.py) against a running Postgres +
configured LLM/embedding provider — see the package README section for setup.
"""
