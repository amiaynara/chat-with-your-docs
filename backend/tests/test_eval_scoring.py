"""Unit tests for the eval harness's scoring logic (issue #13) — no DB, no
provider, just the pure functions that turn raw judge/retrieval output into
scores.
"""

import uuid

from app.eval.scoring import JudgeScore, parse_judge_response, retrieval_hit
from app.qa.answering import Citation


def _citation(snippet: str) -> Citation:
    return Citation(
        document_id=uuid.uuid4(), filename="doc.txt", location_ref="document", snippet=snippet
    )


def test_parse_judge_response_extracts_scores_from_well_formed_json():
    # A "known-good" judge response, matching JUDGE_SYSTEM_PROMPT's requested shape.
    result = parse_judge_response('{"faithfulness": 0.9, "relevancy": 1.0}')

    assert result == JudgeScore(faithfulness=0.9, relevancy=1.0)


def test_parse_judge_response_falls_back_to_zero_on_non_json_output():
    # A "known-bad" judge response — the model ignored the requested format
    # entirely and just wrote prose instead.
    result = parse_judge_response("This answer looks pretty good to me, I'd say a solid 8/10.")

    assert result == JudgeScore(faithfulness=0.0, relevancy=0.0)


def test_parse_judge_response_falls_back_to_zero_on_json_missing_expected_keys():
    result = parse_judge_response('{"faithfulness": 0.9}')

    assert result == JudgeScore(faithfulness=0.0, relevancy=0.0)


def test_parse_judge_response_falls_back_to_zero_on_non_numeric_scores():
    result = parse_judge_response('{"faithfulness": "high", "relevancy": "low"}')

    assert result == JudgeScore(faithfulness=0.0, relevancy=0.0)


def test_parse_judge_response_clamps_out_of_range_scores():
    result = parse_judge_response('{"faithfulness": 1.5, "relevancy": -0.3}')

    assert result == JudgeScore(faithfulness=1.0, relevancy=0.0)


def test_retrieval_hit_is_true_when_a_citation_contains_the_expected_passage():
    citations = [_citation("some unrelated text"), _citation("the answer is 42, definitely")]

    assert retrieval_hit(citations, "the answer is 42") is True


def test_retrieval_hit_is_false_when_no_citation_contains_the_expected_passage():
    citations = [_citation("some unrelated text")]

    assert retrieval_hit(citations, "the answer is 42") is False


def test_retrieval_hit_is_false_with_no_citations_at_all():
    assert retrieval_hit([], "the answer is 42") is False
