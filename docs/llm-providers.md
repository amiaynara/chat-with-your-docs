# LLM providers

Chat answering (`backend/app/qa/answering.py::answer_question`) is a single stateless
call per question — no tool use, no multi-turn agent loop, no Claude Agent SDK/harness.
Your own code does retrieval, assembles a system prompt with the retrieved context, sends
one user message, and gets one text response back via the `LLMProvider` interface
(`backend/app/adapters/llm.py`). Two implementations exist, selected by one config value.

## The two implementations

| | `AnthropicLLMProvider` | `GeminiLLMProvider` |
|---|---|---|
| Model | `claude-haiku-4-5-20251001` (cheapest current Claude model) | `gemini-3.6-flash` |
| Needs | `ANTHROPIC_API_KEY` | `GOOGLE_API_KEY` |
| Cost | per-token API cost (Haiku tier — cheap) | free tier (rate-limited: requests/minute and /day), not unconditionally free |
| SDK | `anthropic` | `google-genai` |

Since answering here is a single request/response call with no agentic behavior, model
choice is purely a quality/cost tradeoff, not a capability question — either provider is a
straightforward drop-in via the shared `LLMProvider` protocol.

**On "free":** Gemini's free tier is real $0 cost up to its quota — genuinely
distinct from Anthropic/OpenAI, neither of which has a no-cost API tier at all. It is not
unlimited; treat it as free-with-a-ceiling, not a permanent zero-cost guarantee at any
volume.

**On model naming:** `gemini-2.5-flash` — the model originally planned here — was
deprecated for new API keys during this work; Google's own API returned a 404 pointing at
`gemini-3.6-flash` instead. Confirmed live against the real API, not assumed. If Gemini
starts failing again later, check whether the configured model name has been retired the
same way — Google's error message names the replacement directly.

## Switching providers

Set in `backend/.env`:

```
LLM_PROVIDER=google          # or "anthropic" (default)
GOOGLE_API_KEY=...
GOOGLE_LLM_MODEL=gemini-3.6-flash
```

No code change needed — `app/providers.py::get_llm_provider()` is the single place that
decides which concrete class to construct; the only caller
(`qa/answering.py::answer_question`) only ever depends on the `LLMProvider` protocol.
`"anthropic"` is the default purely to preserve existing behavior when this switch was
introduced — not a claim that it's the objectively better choice.

Unlike swapping `EMBEDDING_PROVIDER`, this has **no DB/schema impact** — an LLM answer is
plain text, not a stored fixed-width vector, so there's no dimension-consistency guard or
migration/reindex step needed here. Flip the env var, restart the `api` service, done.

## Error handling differences worth knowing

`google-genai`'s errors don't quite match `openai`/`anthropic`'s shape — its `APIError`
exposes the HTTP status as `.code`, not `.status_code`. `classify_provider_call()`
(`backend/app/adapters/retry.py`) takes a `status_code_attr` parameter for exactly this
(defaults to `"status_code"`, `GeminiLLMProvider` passes `"code"`), so the same
transient-vs-permanent retry policy (429/5xx retried with bounded backoff, everything else
fails fast) applies uniformly across all three provider adapters without a bespoke
reimplementation per SDK.

Also unlike `openai`/`anthropic`, `google-genai` has no distinct `RateLimitError`/
`APITimeoutError` types of its own — a 429 arrives as a `ClientError` (handled via
`status_error_type`), and low-level connection/timeout failures surface as the underlying
`httpx` exceptions directly, since the SDK is built on httpx.
