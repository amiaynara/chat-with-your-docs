# Chat With Your Docs

A RAG assistant for asking questions over your own uploaded documents (PDF/txt/Markdown).

Backend: FastAPI + Celery (Python). Frontend: Vite + React + TypeScript + Tailwind.

## Running locally

Document ingestion (embeddings) runs fully key-free by default — `EMBEDDING_PROVIDER=local` runs
a local embedding model (`sentence-transformers`, no API key, no cost, comparable retrieval
quality) out of the box, no setup required. Q&A (the LLM) still calls out to Anthropic by
default. Copy `backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY` if you want
questions to actually get answered instead of failing with a clear "missing credentials" error —
`docker compose up` still works fully without it (upload, ingestion, and status tracking all
work; only the answer step needs a real key).

Want higher-quality (paid, hosted) embeddings instead of the local default? Set
`EMBEDDING_PROVIDER=openai` and `OPENAI_API_KEY` — see `docs/embeddings.md` for the tradeoffs and
why this is a real schema change, not just a config flip.

No Anthropic key/budget? Set `LLM_PROVIDER=google` instead — chat then answers via Google
Gemini, which has a real (rate-limited) free tier. See `docs/llm-providers.md`.

Retrieval combines vector and keyword search by default (no extra setup/keys needed). An
optional reranking step on top of that is off by default; set `RERANKER_ENABLED=true` and
`COHERE_API_KEY` to turn it on. See `docs/architecture.md`'s ticket ledger for both.

Provider credentials above are resolved through a `SecretManager` adapter first (`local`, reading
a gitignored `backend/.secrets` file, or `aws` for AWS Secrets Manager — set via `SECRET_MANAGER`),
falling back to the `.env`/environment values above when a key isn't set there — see
`docs/secrets.md`.

```
docker compose up
```

This starts:

- `api` — FastAPI app on http://localhost:8000 (health check: `GET /health`; interactive API docs: http://localhost:8000/docs, or http://localhost:8000/redoc)
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

### Evaluation harness

Measures retrieval hit-rate and LLM-as-judge faithfulness/relevancy against a small golden Q&A
set, run through both the vector-only and vector+rerank pipeline modes so the reranker's
contribution is a measured number, not just an assumption. See `backend/app/eval/`.

```
cd backend
uv run python -m app.eval
```

Also runs as its own CI job on every push (`eval` in `.github/workflows/ci.yml`), publishing the
same report to the job summary — but only when `GOOGLE_API_KEY` and `COHERE_API_KEY` are
configured as repo secrets. Embeddings need no secret at all (`EMBEDDING_PROVIDER` defaults to
`local`, which the pgvector schema is provisioned to match — see `docs/embeddings.md`). The
LLM-as-judge step uses the free `LLM_PROVIDER=google` option instead of the paid Anthropic
default, so the only unavoidable paid dependency is Cohere — it's the only reranker this app
implements, needed for the harness's vector-vs-vector+rerank comparison. Without those two
secrets configured, the job is skipped, not failed — as shipped here, that's the current state,
so the harness runs manually but not yet in this repo's actual CI until they're added.

## Frontend development (without Docker)

Requires Node >= 22 (see `frontend/.nvmrc`).

```
cd frontend
npm install --legacy-peer-deps
npm run dev
npm run test:coverage  # 100% statements/branches/functions/lines, enforced via vite.config.ts
```

## Production deployment (deferred)

This submission runs locally only (`docker compose up`) — no live/hosted deployment, by design
(see issue #1's Out of Scope). `docs/architecture.md`'s [AWS deployment
topology](docs/architecture.md#aws-deployment-topology-infra-issue-23) documents the intended
production target (ALB + ECS Fargate, RDS Postgres/pgvector, ElastiCache Redis, S3, Secrets
Manager, CloudWatch) with a full diagram, and `infra/`'s AWS CDK app provisions all of it as real,
runnable code — `cdk deploy` would stand it up against a real AWS account; nobody has run it
against one. Getting to an actual live deployment is separate work, tracked as concrete issues
rather than left as an implicit promise:

- **[Infrastructure as Code](https://github.com/NP-Assignments-Labs/fde-amiay-narayan-41f10caa/issues/23)** — ✅ built: `infra/` (AWS CDK, Python) provisions the whole reference architecture; see `infra/README.md` for deploy steps and hardening notes, and `docs/architecture.md` for the topology diagram.
- **[Health checks](https://github.com/NP-Assignments-Labs/fde-amiay-narayan-41f10caa/issues/24)** — ✅ built as part of the same CDK stack: the ALB target group's health check targets the existing `GET /health`.
- **[Auth](https://github.com/NP-Assignments-Labs/fde-amiay-narayan-41f10caa/issues/25)** — real user accounts and multi-tenant data isolation, replacing the current anonymous-session-cookie-only model.
- **[Rate limiting](https://github.com/NP-Assignments-Labs/fde-amiay-narayan-41f10caa/issues/26)** — per-session/per-IP throttling on upload and chat, both for abuse protection and to bound real provider API cost once this is publicly reachable.
- **[Secrets management (production cutover)](https://github.com/NP-Assignments-Labs/fde-amiay-narayan-41f10caa/issues/27)** — the code-level adapter (`SecretManager`, `docs/secrets.md`) and the CDK stack's least-privilege IAM role + placeholder Secrets Manager entries both now exist; what's still deferred is the real AWS account, real key values, and a rotation policy.
- **[Live cutover](https://github.com/NP-Assignments-Labs/fde-amiay-narayan-41f10caa/issues/28)** — actually standing up the provisioned infrastructure, pointing traffic at it, and a rollback plan.
