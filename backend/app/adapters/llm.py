from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic

from app.adapters.retry import classify_provider_call, with_provider_retry


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class AnswerResult:
    text: str
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    def generate(self, system: str, messages: list[Message]) -> AnswerResult:
        """Generate a response given a system prompt and conversation turns."""
        ...


class AnthropicLLMProvider:
    def __init__(
        self, api_key: str, model: str = "claude-sonnet-5", timeout_seconds: float = 30.0
    ) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)

    @with_provider_retry
    def generate(self, system: str, messages: list[Message]) -> AnswerResult:
        response = classify_provider_call(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            ),
            transient_exceptions=(
                anthropic.RateLimitError,
                anthropic.APITimeoutError,
                anthropic.APIConnectionError,
            ),
            status_error_type=anthropic.APIStatusError,
        )

        text = "".join(block.text for block in response.content if block.type == "text")
        return AnswerResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
