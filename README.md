# Chat With Your Docs

A RAG assistant for asking questions over your own uploaded documents (PDF/txt/Markdown).

Backend: FastAPI + Celery (Python). Frontend: Vite + React + TypeScript + Tailwind.

## Running locally

Document ingestion (embeddings) and Q&A (the LLM) call out to OpenAI and Anthropic. Copy
`backend/.env.example` to `backend/.env` and set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` if you want
uploads to actually reach `ready` instead of failing with a clear "missing credentials" error —
`docker compose up` still works fully without them (upload, validation, and status tracking all
work; only the embedding/answer step needs real keys).

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
uv run pytest -q
uv run uvicorn app.main:app --reload
```

## Frontend development (without Docker)

Requires Node >= 22 (see `frontend/.nvmrc`).

```
cd frontend
npm install --legacy-peer-deps
npm run dev
```
