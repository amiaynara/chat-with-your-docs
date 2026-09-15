# Chat With Your Docs

A RAG assistant for asking questions over your own uploaded documents (PDF/txt/Markdown).

Backend: FastAPI + Celery (Python). Frontend: Vite + React + TypeScript + Tailwind.

## Running locally

Document ingestion (embeddings) and Q&A (the LLM) call out to OpenAI and Anthropic. Copy
`backend/.env.example` to `backend/.env` and set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` if you want
uploads to actually reach `ready` instead of failing with a clear "missing credentials" error —
`docker compose up` still works fully without them (upload, validation, and status tracking all
work; only the embedding/answer step needs real keys).

No OpenAI key/credits? Set `EMBEDDING_PROVIDER=local` instead — ingestion then runs a local
embedding model (`sentence-transformers`, no API key, no cost, comparable retrieval quality).
See `docs/embeddings.md` for the tradeoffs and how to switch.

No Anthropic key/budget? Set `LLM_PROVIDER=google` instead — chat then answers via Google
Gemini, which has a real (rate-limited) free tier. See `docs/llm-providers.md`.

Retrieval combines vector and keyword search by default (no extra setup/keys needed). An
optional reranking step on top of that is off by default; set `RERANKER_ENABLED=true` and
`COHERE_API_KEY` to turn it on. See `docs/architecture.md`'s ticket ledger for both.

```
docker compose up
```

This starts:

- `api` — FastAPI app on http://localhost:8000 (health check: `GET /health`)
- `worker` — Celery worker (background document ingestion)
- `postgres` — Postgres 16 with the `pgvector` extension, published on host port `5433` (not the default `5432`, to avoid clashing with a locally-installed Postgres)
- `redis` — Celery broker/result backend
- `minio` — S3-compatible object storage for uploaded files (console on http://localhost:9001)
- `frontend` — Vite dev server on http://localhost:5173

> Full architecture overview, technical decisions, and productionization notes will be filled in as the build progresses (see `ASSIGNMENT.md` for what's required at submission time).

## Backend development (without Docker)

Requires `postgres`, `redis`, and `minio` running (e.g. `docker compose up -d postgres redis minio`).

```
cd backend
uv sync --group dev
uv run alembic upgrade head
uv run pytest -q                                    # fast suite (fakes only, no live services)
uv run uvicorn app.main:app --reload
```

Coverage: the fast suite alone won't show 100%, because the real provider adapters'
network-client code paths (e.g. `S3ObjectStorage` actually talking to MinIO) are only
exercised by the `integration`-marked tests, which need `postgres` and `minio` running
(`docker compose up -d postgres redis minio`). Together they're 100%, enforced via
`fail_under = 100` in `pyproject.toml`:

```
uv run pytest -m "integration or not integration" --cov=app --cov-report=term-missing
```

## Frontend development (without Docker)

Requires Node >= 22 (see `frontend/.nvmrc`).

```
cd frontend
npm install --legacy-peer-deps
npm run dev
npm run test:coverage  # 100% statements/branches/functions/lines, enforced via vite.config.ts
```
