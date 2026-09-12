# Chat With Your Docs

A RAG assistant for asking questions over your own uploaded documents (PDF/txt/Markdown).

Backend: FastAPI + Celery (Python). Frontend: Vite + React + TypeScript + Tailwind.

## Running locally

```
docker compose up
```

This starts:

- `api` — FastAPI app on http://localhost:8000 (health check: `GET /health`)
- `worker` — Celery worker (background document ingestion)
- `postgres` — Postgres 16 with the `pgvector` extension
- `redis` — Celery broker/result backend
- `minio` — S3-compatible object storage for uploaded files (console on http://localhost:9001)
- `frontend` — Vite dev server on http://localhost:5173

> Full architecture overview, technical decisions, and productionization notes will be filled in as the build progresses (see `ASSIGNMENT.md` for what's required at submission time).

## Backend development (without Docker)

```
cd backend
uv sync --group dev
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
