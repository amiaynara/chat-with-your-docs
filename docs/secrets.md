# Secret manager

Every external provider dependency in this app (LLM, embeddings, reranker, object storage)
already sits behind a swappable adapter interface (`EmbeddingProvider`, `LLMProvider`,
`RerankerProvider`, `ObjectStorage` — see `backend/app/adapters/`, selected via
`app/providers.py`'s `get_*()` factories and a config toggle). Secret *retrieval* gets the same
shape here: a `SecretManager` adapter (`backend/app/adapters/secrets.py`), selected by one config
value, with two implementations.

## The two implementations

| | `LocalSecretManager` | `AWSSecretManager` |
|---|---|---|
| Reads from | a local, gitignored `KEY=value`-per-line file | AWS Secrets Manager (via `boto3`) |
| Needs | nothing — zero setup | an AWS account + credentials (an IAM role in production) |
| Where it runs | this machine | AWS's servers |
| Deployment target | local dev (`docker compose up`) | the AWS reference architecture (`docs/architecture.md`, issue #16) |

`local` is the default — matching how this app runs fully offline/key-free wherever possible
(e.g. `EMBEDDING_PROVIDER=local`'s default, `docs/embeddings.md`).

## Switching implementations

Set in `backend/.env` (or `.env.docker` for defaults shared by everyone):

```
SECRET_MANAGER=local              # or "aws"
LOCAL_SECRETS_FILE=.secrets       # only used by "local"
AWS_SECRETS_REGION=us-east-1      # only used by "aws"
```

No code change needed — `app/providers.py::get_secret_manager()` is the single place that
decides which concrete class to construct; any caller only ever depends on the `SecretManager`
protocol (`get_secret(name: str) -> str`, raising `SecretNotFoundError` — never `None`/`""` — for
a missing/unresolvable secret).

### `LocalSecretManager`'s file format

One `KEY=value` pair per line, e.g.:

```
ANTHROPIC_API_KEY=sk-ant-...
COHERE_API_KEY=co-...
```

Blank lines and lines starting with `#` are ignored; surrounding whitespace around the key and
value is stripped. The file is read once, at construction. It's expected at `backend/.secrets` by
default (already in `.gitignore` — never commit a real secret into it), separate from
`backend/.env`: `.env` is pydantic-settings' own implicit environment-variable loading (see
"Resolution order" below), while this file is an explicit, adapter-owned read with no framework
magic — the same "swap the implementation, not the shape" reasoning that already applies to
`ObjectStorage`/`EmbeddingProvider`/etc.

A missing file is not a construction error (this app runs key-free out of the box); only asking
for a secret that was never defined raises `SecretNotFoundError`.

### `AWSSecretManager`

Reads via `boto3`'s Secrets Manager client, using the same bounded-retry/timeout convention as
`S3ObjectStorage` (`app/adapters/retry.py`): transient failures (timeouts, 5xx) retry with
backoff; `AccessDeniedException`/`InvalidRequestException`/`InvalidParameterException`/
`DecryptionFailure` fail immediately (retrying can't fix them);
`ResourceNotFoundException` (no such secret) raises `SecretNotFoundError` rather than being
retried at all — a missing secret name isn't a transient condition.

Unlike `S3ObjectStorage`, this adapter takes no `access_key`/`secret_key` constructor arguments —
credentials come from `boto3`'s normal resolution chain (an IAM role for the AWS deployment
target in `docs/architecture.md`; `~/.aws/*` or environment variables for local use against a real
AWS account). Secret retrieval is exactly the kind of credential that chain exists to keep out of
application config in the first place.

## Resolution order: how this relates to the existing `*_API_KEY` settings

`app/config.py`'s `Settings` still loads `anthropic_api_key`/`openai_api_key`/`google_api_key`/
`cohere_api_key` from `.env`/the environment exactly as before — `SecretManager` doesn't replace
that loading, it's layered **in front of** it as the preferred source, with the `Settings` value
kept as a fallback:

- `app/providers.py`'s `get_llm_provider()`, `get_embedding_provider()`, and
  `get_reranker_provider()` each resolve their API key via a shared `_resolve_secret(name,
  fallback)` helper: `get_secret_manager().get_secret(name)` first, falling back to the matching
  `Settings` value only if the secret manager raises `SecretNotFoundError` for that name (e.g. the
  key isn't present in `backend/.secrets`, or `local_secrets_file` points at a file that doesn't
  exist — the zero-setup default).
- Concretely: `ANTHROPIC_API_KEY` → `_resolve_secret("ANTHROPIC_API_KEY", settings.anthropic_api_key)`,
  and likewise for `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `COHERE_API_KEY`. Object storage's
  credentials (`OBJECT_STORAGE_ACCESS_KEY`/`OBJECT_STORAGE_SECRET_KEY`) are deliberately **not**
  wired through this — those are local MinIO dev defaults, not a production secret this ticket's
  `backend/.secrets` file is meant to hold; `get_object_storage()` is unchanged.
- This means either source works standalone: put a key only in `backend/.secrets` (or AWS Secrets
  Manager, with `SECRET_MANAGER=aws`) and drop it from `.env`, or keep it only in `.env` as before
  — both resolve to the same credential reaching the provider adapter. Setting a key in *both*
  places is harmless; the secret manager wins.
- Why a fallback instead of making the secret manager the sole source: this app is meant to keep
  running key-free out of the box (`docs/embeddings.md`'s `EMBEDDING_PROVIDER=local` default,
  README's "works fully without a key" framing) — a bare `SecretNotFoundError` bubbling out of
  `get_llm_provider()` on every request with no `ANTHROPIC_API_KEY` configured anywhere would trade
  a clear, existing "missing credentials" failure (a real API call returning 401, surfaced by
  `qa/answering.py`) for a different failure at construction time, for no behavioral benefit — the
  fallback keeps that behavior identical whichever source (or neither) is configured.

`get_object_storage()` and the rest of `Settings` (non-secret config like `chunk_size_chars`,
`retrieval_top_k`, …) are untouched — this only applies to the four provider API keys above.

## Tests

- `tests/fakes/secrets.py::FakeSecretManager` — an in-memory fake for the fast test suite, same
  shape as `tests/fakes/storage.py`'s `FakeObjectStorage`.
- `tests/test_secrets_adapter.py` — `LocalSecretManager` tested directly against fixture files
  (`tmp_path`); `_classify_client_error` and `AWSSecretManager`'s error-translation behavior tested
  directly by monkeypatching the underlying `boto3` client (no marker needed — unlike
  `S3ObjectStorage`, constructing `AWSSecretManager` makes no network call, so these need no real
  or mocked AWS at all); and a round-trip/not-found contract test exercising the real `boto3`
  Secrets Manager code path against `moto`'s mocked AWS backend (the "moto" alternative the ticket
  calls out), marked `integration` (excluded from the default `-m 'not integration'` run — run with
  `uv run pytest -m integration`) since it's still the real-SDK contract-test layer, not our own
  fake, even though it needs no real AWS account to run.
