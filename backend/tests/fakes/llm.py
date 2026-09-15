import re

from app.adapters.llm import AnswerResult, Message

# Anchored on a newline right after the opening tag (exactly how
# qa/answering.py's _SYSTEM_TEMPLATE renders it) rather than bare "<context>" —
# the template's own instructions prose mentions "the <context> block" inline,
# which a bare-tag regex's first match would latch onto instead of the real tag.
_CONTEXT_BLOCK = re.compile(r"<context>\n(.*?)\n</context>", re.DOTALL)


class FakeLLMProvider:
    """Deterministic extractive 'answering' — no real network calls.

    Picks the sentence from the assembled context that shares the most words
    with the latest user question. This lets tests assert an answer is
    genuinely grounded in retrieved context (not a real model's knowledge),
    without needing a live LLM.
    """

    def __init__(self) -> None:
        self.last_system: str | None = None
        self.last_messages: list[Message] | None = None

    def generate(self, system: str, messages: list[Message]) -> AnswerResult:
        self.last_system = system
        self.last_messages = messages

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
