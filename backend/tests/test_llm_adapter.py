"""Unit tests for AnthropicLLMProvider with the anthropic client mocked at
the SDK boundary — no real network call, no API key needed.

Error-classification behavior itself is covered directly in
test_retry.py; this just proves generate() assembles the request and
extracts the response correctly on success.
"""

from types import SimpleNamespace

from app.adapters.llm import AnthropicLLMProvider, Message


def test_generate_extracts_text_and_token_usage():
    provider = AnthropicLLMProvider(api_key="fake-key")

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
    provider = AnthropicLLMProvider(api_key="fake-key")

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
