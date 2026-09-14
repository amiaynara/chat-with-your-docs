"""Unit tests for the LLMProvider adapters with their real SDK client mocked at the
boundary — no real network call, no API key needed.

Error-classification behavior itself is covered directly in test_retry.py; these just
prove generate() assembles the request and extracts the response correctly on success.
"""

from types import SimpleNamespace

from app.adapters.llm import AnthropicLLMProvider, GeminiLLMProvider, Message


def test_generate_extracts_text_and_token_usage():
    provider = AnthropicLLMProvider(api_key="fake-key", model="claude-haiku-4-5-20251001")

    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Hello there.")],
        usage=SimpleNamespace(input_tokens=12, output_tokens=4),
    )
    provider._client.messages.create = lambda **kwargs: fake_response

    result = provider.generate(
        system="You are a helpful assistant.",
        messages=[Message(role="user", content="Hi")],
    )

    assert result.text == "Hello there."
    assert result.input_tokens == 12
    assert result.output_tokens == 4


def test_generate_ignores_non_text_content_blocks():
    provider = AnthropicLLMProvider(api_key="fake-key", model="claude-haiku-4-5-20251001")

    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(type="tool_use", text=None),
            SimpleNamespace(type="text", text="The answer."),
        ],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    provider._client.messages.create = lambda **kwargs: fake_response

    result = provider.generate(system="system", messages=[Message(role="user", content="Hi")])

    assert result.text == "The answer."


def test_gemini_generate_extracts_text_and_token_usage():
    provider = GeminiLLMProvider(api_key="fake-key", model="gemini-3.6-flash")

    fake_response = SimpleNamespace(
        text="Hello there.",
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=4),
    )
    provider._client.models.generate_content = lambda **kwargs: fake_response

    result = provider.generate(
        system="You are a helpful assistant.",
        messages=[Message(role="user", content="Hi")],
    )

    assert result.text == "Hello there."
    assert result.input_tokens == 12
    assert result.output_tokens == 4


def test_gemini_generate_maps_our_assistant_role_to_geminis_model_role():
    provider = GeminiLLMProvider(api_key="fake-key", model="gemini-3.6-flash")
    captured = {}

    def _fake_generate_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text="ok",
            usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
        )

    provider._client.models.generate_content = _fake_generate_content

    provider.generate(
        system="sys",
        messages=[
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello!"),
        ],
    )

    assert [content.role for content in captured["contents"]] == ["user", "model"]


def test_gemini_generate_defaults_to_empty_text_and_zero_usage_without_metadata():
    provider = GeminiLLMProvider(api_key="fake-key", model="gemini-3.6-flash")
    provider._client.models.generate_content = lambda **kwargs: SimpleNamespace(
        text=None, usage_metadata=None
    )

    result = provider.generate(system="sys", messages=[Message(role="user", content="Hi")])

    assert result.text == ""
    assert result.input_tokens == 0
    assert result.output_tokens == 0
