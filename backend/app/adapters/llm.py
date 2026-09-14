from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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
    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
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


class GeminiLLMProvider:
    """LLM answering via Google Gemini — a free-tier (rate-limited, not unconditionally
    free) alternative to Anthropic. See docs/llm-providers.md for the tradeoffs.
    """

    # Our Message.role uses "assistant" (matching Anthropic/OpenAI convention); Gemini
    # expects "model" for that same turn.
    _ROLE_MAP = {"user": "user", "assistant": "model"}

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self._model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )

    @with_provider_retry
    def generate(self, system: str, messages: list[Message]) -> AnswerResult:
        contents = [
            genai_types.Content(
                role=self._ROLE_MAP[m.role], parts=[genai_types.Part(text=m.content)]
            )
            for m in messages
        ]
        response = classify_provider_call(
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system, max_output_tokens=1024
                ),
            ),
            # The SDK is built on httpx; unlike openai/anthropic it has no distinct
            # RateLimitError/APITimeoutError types of its own — a 429 arrives as a
            # ClientError (caught below via status_error_type), transport-level
            # failures as raw httpx exceptions.
            transient_exceptions=(httpx.ConnectError, httpx.TimeoutException),
            status_error_type=genai_errors.APIError,
            # google-genai's APIError exposes the HTTP status as `.code`, not
            # `.status_code` (see retry.py's status_code_attr).
            status_code_attr="code",
        )

        usage = response.usage_metadata
        return AnswerResult(
            text=response.text or "",
            input_tokens=(usage.prompt_token_count if usage else None) or 0,
            output_tokens=(usage.candidates_token_count if usage else None) or 0,
        )
