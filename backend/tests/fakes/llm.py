import json
import re

from app.adapters.llm import AnswerResult, Message

# Anchored on a newline right after the opening tag (exactly how
# qa/answering.py's _SYSTEM_TEMPLATE renders it) rather than bare "<context>" —
# the template's own instructions prose mentions "the <context> block" inline,
# which a bare-tag regex's first match would latch onto instead of the real tag.
_CONTEXT_BLOCK = re.compile(r"<context>\n(.*?)\n</context>", re.DOTALL)

# app.eval.scoring.JUDGE_SYSTEM_PROMPT is the only system prompt in this app
# that asks for both of these — a plain marker, not a tight coupling to its
# exact wording, so this fake keeps working if that prompt's phrasing changes.
_JUDGE_MARKERS = ("faithfulness", "relevancy")
_JUDGE_SECTIONS = re.compile(
    r"Question:\s*(?P<question>.*?)\nContext:\s*(?P<context>.*?)\nAnswer:\s*(?P<answer>.*)",
    re.DOTALL,
)


class FakeLLMProvider:
    """Deterministic extractive 'answering' — no real network calls.

    Picks the sentence from the assembled context that shares the most words
    with the latest user question. This lets tests assert an answer is
    genuinely grounded in retrieved context (not a real model's knowledge),
    without needing a live LLM.

    Doubles as a deterministic judge for app.eval.harness's LLM-as-judge step
    (see _judge below) — the same fake instance stands in for whichever real
    role the caller invokes it for, same as this fixture already does for
    plain answering.
    """

    def __init__(self) -> None:
        self.last_system: str | None = None
        self.last_messages: list[Message] | None = None

    def generate(self, system: str, messages: list[Message]) -> AnswerResult:
        self.last_system = system
        self.last_messages = messages

        if all(marker in system.lower() for marker in _JUDGE_MARKERS):
            return _judge(messages[-1].content if messages else "")

        question = messages[-1].content if messages else ""
        context_match = _CONTEXT_BLOCK.search(system)
        context = context_match.group(1).strip() if context_match else ""

        if not context.strip():
            text = "I don't have any supporting information to answer that."
        else:
            text = _best_matching_sentence(context, question)

        return AnswerResult(
            text=text,
            input_tokens=len(system.split()),
            output_tokens=len(text.split()),
        )


def _judge(content: str) -> AnswerResult:
    """Deterministic word-overlap 'judging': faithfulness is the fraction of
    the answer's words also present in the context (a hallucinated word has
    nowhere to come from but outside it); relevancy is the fraction of the
    answer's words also present in the question (an on-topic answer echoes
    the question's own vocabulary back). The same overlap signal every other
    fake here (embeddings, reranker) already uses in place of a real model.
    """
    match = _JUDGE_SECTIONS.search(content)
    question = match.group("question").strip() if match else ""
    context = match.group("context").strip() if match else ""
    answer = match.group("answer").strip() if match else ""

    answer_words = set(_words(answer))
    payload = json.dumps(
        {
            "faithfulness": _overlap_ratio(answer_words, set(_words(context))),
            "relevancy": _overlap_ratio(answer_words, set(_words(question))),
        }
    )
    return AnswerResult(
        text=payload,
        input_tokens=len(content.split()),
        output_tokens=len(payload.split()),
    )


def _overlap_ratio(answer_words: set[str], other_words: set[str]) -> float:
    if not answer_words:
        return 0.0
    return len(answer_words & other_words) / len(answer_words)


def _best_matching_sentence(context: str, question: str) -> str:
    question_words = set(_words(question))
    sentences = re.split(r"(?<=[.!?])\s+", context)
    best_sentence = sentences[0] if sentences else context
    best_score = -1
    for sentence in sentences:
        score = len(question_words & set(_words(sentence)))
        if score > best_score:
            best_score = score
            best_sentence = sentence
    return best_sentence.strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())
