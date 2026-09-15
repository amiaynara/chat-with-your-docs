from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/app"
    redis_url: str = "redis://localhost:6379/0"

    celery_task_always_eager: bool = False

    object_storage_endpoint_url: str = "http://localhost:9000"
    object_storage_access_key: str = "minioadmin"
    object_storage_secret_key: str = "minioadmin"
    object_storage_bucket: str = "documents"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    cohere_api_key: str = ""
    provider_timeout_seconds: float = 30.0

    # Which LLMProvider implementation app.providers.get_llm_provider() constructs —
    # "anthropic" (needs ANTHROPIC_API_KEY) or "google" (Gemini; needs GOOGLE_API_KEY,
    # has a real free tier — see docs/llm-providers.md). "anthropic" is the default
    # purely to preserve existing behavior; it isn't a claim that it's the better
    # choice. Swapping this is a config-only change — no DB/schema impact, unlike
    # swapping EMBEDDING_PROVIDER, since answers are plain text, not a stored vector.
    llm_provider: str = "anthropic"
    # Answering here is a single stateless call per question (see
    # AnthropicLLMProvider.generate) — no tool use, no multi-turn agent loop — so
    # there's no need for a larger reasoning model. Haiku 4.5 is Anthropic's cheapest
    # current model; chosen to minimize per-answer cost for this workload.
    llm_model: str = "claude-haiku-4-5-20251001"
    # gemini-2.5-flash is deprecated for new API keys as of this writing — Google's API
    # itself returns a 404 directing new callers to gemini-3.6-flash. Confirmed live
    # against the real API, not assumed.
    google_llm_model: str = "gemini-3.6-flash"

    # Which EmbeddingProvider implementation app.providers.get_embedding_provider()
    # constructs — "openai" (hosted, needs OPENAI_API_KEY + credits) or "local" (runs
    # on-machine via sentence-transformers, no key/cost, slightly lower retrieval
    # quality). See docs/embeddings.md. Swapping this is a config-only change; the two
    # models produce differently-sized vectors, so embedding_dimensions below must be
    # updated to match and existing chunks re-indexed — see that doc for why.
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_model_version: str = "1"
    embedding_dimensions: int = 1536

    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    local_embedding_model_version: str = "1"

    max_upload_bytes: int = 20 * 1024 * 1024
    allowed_upload_extensions: tuple[str, ...] = (".pdf", ".txt", ".md")

    chunk_size_chars: int = 1000
    chunk_overlap_ratio: float = 0.1

    session_cookie_name: str = "session_id"
    # False only in the test environment (plain-http TestClient) — see
    # tests/conftest.py. Real browsers treat localhost as a secure context and
    # still send Secure cookies over http://localhost, but a bare httpx test
    # client talking to "testserver" does not.
    session_cookie_secure: bool = True

    retrieval_top_k: int = 5
    # Cosine-distance ceiling a retrieved chunk must fall under to count as
    # "supporting evidence" — a starting hypothesis, not a locked constant (mirrors
    # chunk_overlap_ratio above), calibrated against the deterministic fake embedding
    # used in tests (see ChunkRepository.search_ready's docstring — real embedding
    # models aren't guaranteed to bound distance at 1.0 the way that fake is) and
    # meant to be validated/tuned against real embeddings via the eval harness
    # (#12/#13). Below this, answer_question() refuses deterministically (issue #6's
    # no-evidence/out-of-corpus guardrail) rather than asking the LLM to judge
    # relevance itself — a genuinely irrelevant top-k chunk (distance ~1.0 against the
    # fake, for zero vocabulary overlap) is the same signal whether the corpus is
    # empty or just doesn't cover the question.
    retrieval_relevance_threshold: float = 0.9

    # How many of a session's most recent messages (user+assistant combined) are
    # included as conversation history in the prompt for a follow-up question — a
    # starting hypothesis, not locked (same framing as chunk_overlap_ratio/
    # retrieval_relevance_threshold above): keeps prompt size/cost bounded rather
    # than growing unboundedly over a long-running conversation.
    chat_history_max_messages: int = 10

    # Optional pipeline toggle (issue #12): False runs vector→answer (retrieval as
    # shaped above, unchanged); True inserts a rerank step, vector→rerank→answer,
    # re-scoring a larger retrieved candidate pool with a hosted cross-encoder and
    # keeping only the top retrieval_top_k for the prompt. A genuine on/off switch,
    # not a hard dependency — the reranker is never required for the pipeline to
    # run. Off by default: no reranker API key is required to run this app at all.
    reranker_enabled: bool = False
    reranker_model: str = "rerank-v3.5"
    # How many candidates search_ready fetches (per branch — see its docstring)
    # before reranking narrows them down to retrieval_top_k — wider than
    # retrieval_top_k itself so the reranker actually has something to rerank.
    # Irrelevant when reranker_enabled is False, where search_ready is called
    # with retrieval_top_k directly instead.
    rerank_candidate_pool_size: int = 20


settings = Settings()
