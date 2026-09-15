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

`local` is the default — the `chunks.embedding` pgvector column is provisioned at its 384-dim
width by the baseline migration, so this is what a fresh clone runs against out of the box, no
key required. Set in `backend/.env` (or `.env.docker` for defaults shared by everyone) to switch
to OpenAI instead:

```
EMBEDDING_PROVIDER=openai         # or "local" (default)
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

No code change needed — `app/providers.py::get_embedding_provider()` is the single place that
decides which concrete class to construct; every caller (`ingestion/tasks.py`,
`qa/answering.py`) only ever depends on the `EmbeddingProvider` protocol.

**The one thing that isn't free to change: vector size.** `bge-small-en-v1.5` produces 384-dim
vectors; `text-embedding-3-small` produces 1536. The `chunks.embedding` column is a fixed-width
pgvector column, provisioned at 384 by the baseline migration
(`alembic/versions/0002_documents_and_chunks.py` — a hardcoded literal, deliberately *not* read
from `settings.embedding_dimensions` at migration-run time, so the schema's real width can't
silently drift out from under whatever a developer's local `.env` happens to say; see that
migration's own comment). `EMBEDDING_DIMENSIONS` is what `get_embedding_provider()` cross-checks
the configured provider's own real `dimensions` against before constructing it — catching a
provider/setting mismatch immediately with a clear `RuntimeError`, rather than letting it surface
later as an opaque pgvector error inside a Celery task — but changing that setting alone does
**not** change the actual column width; only a migration does that.

So switching from the default (`local`, 384) to `openai` (1536) — on *any* database, fresh or
not, since the column width comes from the migration, not from config — is a deliberate
three-step operation:
1. Update `EMBEDDING_DIMENSIONS` to match the new provider (1536 for OpenAI's
   `text-embedding-3-small`; a different model may differ — each provider reports its own real
   `dimensions`, inferred from the loaded model for `LocalEmbeddingProvider` and looked up from a
   known model → dimension table for `OpenAIEmbeddingProvider`).
2. Write and run a migration resizing the `chunks.embedding` column to match.
3. Re-ingest existing documents — old chunks' vectors were produced by a different model and are
   not comparable to new ones. (Every chunk already records `embedding_model`/`embedding_version`
   for exactly this reason — the "indexing contract" mentioned in issue #1.)

On a genuinely empty database (nothing ingested yet), step 3 is moot, but step 2 (the migration)
is never optional — there is no config-only way to get a different column width.

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
