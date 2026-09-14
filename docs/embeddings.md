# Embedding providers

Ingestion turns each document chunk into a vector (`Chunk.embedding`, `backend/app/models.py`)
so retrieval can find semantically relevant passages by vector similarity
(`ChunkRepository.search_ready`, cosine distance). Producing that vector requires a model —
this app supports two, behind the `EmbeddingProvider` interface
(`backend/app/adapters/embeddings.py`), selected by one config value.

## The two implementations

| | `OpenAIEmbeddingProvider` | `LocalEmbeddingProvider` |
|---|---|---|
| Model | `text-embedding-3-small` (hosted) | `BAAI/bge-small-en-v1.5` (local, via `sentence-transformers`) |
| Needs | `OPENAI_API_KEY` + API credits | nothing — runs on-machine |
| Cost | per-token API cost | free |
| Vector size | 1536 | 384 |
| Retrieval quality (MTEB avg, English) | ~62 | ~62 — roughly at parity |
| Latency | network round-trip per call | CPU inference, no network |
| Where it runs | OpenAI's servers | this machine (CPU; no GPU needed or used) |

Both are genuine semantic embedding models (transformer bi-encoders trained via contrastive
learning) — this isn't a quality-vs-no-quality tradeoff, `bge-small-en-v1.5` benchmarks roughly
even with `text-embedding-3-small` on standard retrieval benchmarks (MTEB) despite being ~1000x
smaller. The real tradeoffs are operational: needing an API key/budget vs. a heavier local
dependency (`sentence-transformers` + a CPU build of `torch`) and a one-time model download.

## Switching providers

Set in `backend/.env` (or `.env.docker` for defaults shared by everyone):

```
EMBEDDING_PROVIDER=local          # or "openai" (default)
LOCAL_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
LOCAL_EMBEDDING_MODEL_VERSION=1
```

No code change needed — `app/providers.py::get_embedding_provider()` is the single place that
decides which concrete class to construct; every caller (`ingestion/tasks.py`,
`qa/answering.py`) only ever depends on the `EmbeddingProvider` protocol.

**The one thing that isn't free to change: vector size.** `text-embedding-3-small` produces
1536-dim vectors; `bge-small-en-v1.5` produces 384. The `chunks.embedding` column is a
fixed-width pgvector column (`Vector(settings.embedding_dimensions)`), provisioned once via an
Alembic migration — it can't silently hold both sizes. Each provider reports its own real
`dimensions` rather than trusting config: `OpenAIEmbeddingProvider` looks it up from a known
model → dimension table (`text-embedding-3-small` → 1536, `text-embedding-3-large` → 3072,
`text-embedding-ada-002` → 1536; an unrecognized `EMBEDDING_MODEL` raises immediately), and
`LocalEmbeddingProvider` reads it straight off the loaded model. `get_embedding_provider()` then
cross-checks that real value against `EMBEDDING_DIMENSIONS` and raises a `RuntimeError`
immediately (before anything tries to embed) naming exactly what's mismatched, rather than
letting it surface later as an opaque pgvector error inside a Celery task.

So switching providers on an existing database is a deliberate three-step operation, not a
config-only flip:
1. Update `EMBEDDING_DIMENSIONS` to match the new provider (1536 for OpenAI, 384 for
   `bge-small-en-v1.5`; a different local model may differ — its `dimensions` is inferred from
   the loaded model itself, not hardcoded).
2. Write and run a migration resizing the `chunks.embedding` column.
3. Re-ingest existing documents — old chunks' vectors were produced by a different model and are
   not comparable to new ones. (Every chunk already records `embedding_model`/`embedding_version`
   for exactly this reason — the "indexing contract" mentioned in issue #1.)

On a fresh/empty database (nothing ingested yet), steps 2–3 are moot — just set both env vars
before the first upload.

## Local model caching (Docker)

`LocalEmbeddingProvider` downloads its weights from Hugging Face Hub the first time it's
constructed (~130MB for `bge-small-en-v1.5`), then caches them. `docker-compose.yml` mounts a
named volume (`hf_cache`) at `HF_HOME=/opt/hf-cache` on both `api` and `worker` (both construct an
embedding provider — ingestion in the worker, and query-time embedding for chat in the api), so
that download happens once, not on every container restart. Needs internet the first time only;
fully offline after.

## Why `sentence-transformers`/`torch` are pinned to a CPU-only build

`LocalEmbeddingProvider` never needs a GPU — this app has no other use for one, and Docker
Desktop doesn't pass one into containers anyway. The default PyPI `torch` wheel pulls in CUDA
runtime libraries as transitive dependencies regardless (multiple GB, entirely unused here), so
`backend/pyproject.toml` pins `torch` to the official CPU-only wheel index
(`https://download.pytorch.org/whl/cpu`) via `[tool.uv.sources]`.

## Known limitation: the model reloads on every call (issue #20)

`get_embedding_provider()` constructs a fresh `LocalEmbeddingProvider` — and therefore
reloads the whole model into memory — on every call, not once per process. Measured live:
~40s of a ~48s ingestion is torch import + model construction, repeating on every
upload/question rather than being paid once. Deliberately left unfixed for now — see
**issue #20** for the full breakdown and the fix-vs-accept tradeoff (a process-level
model cache is the likely fix, but needs a deliberate look at how that interacts with
Celery's forking worker model before anyone implements it).
