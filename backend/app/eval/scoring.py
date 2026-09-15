import json
from dataclasses import dataclass

from app.qa.answering import Citation

# Asks the judge LLM to score an already-generated answer along two axes and
# to respond with nothing but the JSON parse_judge_response below expects.
# Kept as plain prose (no schema/tool-use) since every LLMProvider here
# (app/adapters/llm.py) exposes the same plain generate(system, messages) ->
# text shape, with no structured-output mode to lean on.
JUDGE_SYSTEM_PROMPT = """You are grading a RAG system's answer for quality. You will be given \
the question that was asked, the retrieved context the system had available, and the answer it \
produced.

Score two things, each a number from 0.0 to 1.0:
- faithfulness: does the answer only state things supported by the context, with no invented
  detail?
- relevancy: does the answer actually address the question that was asked?

Respond with ONLY a JSON object of the exact shape {"faithfulness": <number>, "relevancy": \
<number>} — no other text, no markdown fencing."""


@dataclass(frozen=True)
class JudgeScore:
    faithfulness: float
    relevancy: float


def parse_judge_response(text: str) -> JudgeScore:
    """Parse the judge LLM's raw response (expected shape: JUDGE_SYSTEM_PROMPT's
    JSON object) into a JudgeScore.

    A response that doesn't actually match that shape — the judge model
    ignored the format, wrapped it in prose/markdown, or an adapter returned
    an empty string — scores 0.0 on both axes rather than raising: one
    malformed judge call shouldn't crash a run against the whole golden set,
    and 0.0 is the safe direction for a quality metric to fail toward (an
    ungraded item reads as "no evidence of quality" rather than silently
    inflating an average).
    """
    try:
        data = json.loads(text)
        faithfulness = float(data["faithfulness"])
        relevancy = float(data["relevancy"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JudgeScore(faithfulness=0.0, relevancy=0.0)
    return JudgeScore(faithfulness=_clamp(faithfulness), relevancy=_clamp(relevancy))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def retrieval_hit(citations: list[Citation], expected_passage: str) -> bool:
    """Whether the golden item's supporting passage actually made it into the
    context the LLM was given — i.e. whether any citation (exactly the chunks
    placed in the prompt, per qa/answering.py) contains `expected_passage`.

    Checked against the citation, not the final answer text: retrieval
    quality (did the right chunk get retrieved and kept?) and generation
    quality (did the LLM phrase a good answer from it?) are different
    failure modes, and the latter is already covered by the faithfulness/
    relevancy judge scores.
    """
    return any(expected_passage in citation.snippet for citation in citations)
