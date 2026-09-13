import os

from sqlalchemy.engine import make_url

_DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/app"


def _force_test_database_url() -> None:
    """Point tests at a dedicated `<db>_test` database — never the real one.

    Regression guard: tests used to build their schema with
    Base.metadata.create_all() against whatever DATABASE_URL resolved to,
    which by default is the exact same database docker-compose's postgres
    service and Alembic manage. That silently created the enum types/tables
    without Alembic ever knowing, so alembic_version stayed behind — a later
    `docker compose up` re-running `alembic upgrade head` against that same
    database then failed with "type already exists" (the type was already
    there, alembic just didn't know it). Forcing every test run onto its own
    database, built via the real Alembic migrations below, makes that
    divergence impossible regardless of what DATABASE_URL happens to be set
    to in the shell/CI environment.

    Must run before anything imports app.config (which reads DATABASE_URL at
    import time) — hence this being the first thing this file does.
    """
    url = make_url(os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL))
    if not url.database.endswith("_test"):
        url = url.set(database=f"{url.database}_test")
    # str(url) masks the password (renders it as "***") — it's meant for safe
    # logging, not for producing a connection string to actually use.
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)


_force_test_database_url()

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from alembic import command  # noqa: E402
from app import (  # noqa: E402
    models,  # noqa: F401  (registers ORM models on Base.metadata)
    providers,
)
from app.celery_app import celery_app  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from tests.fakes.embeddings import FakeEmbeddingProvider  # noqa: E402
from tests.fakes.llm import FakeLLMProvider  # noqa: E402
from tests.fakes.storage import FakeObjectStorage  # noqa: E402

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

# TestClient talks plain http to "testserver" — a Secure cookie would never be
# stored/resent by httpx's cookie jar (unlike a real browser, which treats
# localhost as a secure context). Real dev/prod keep secure=True.
settings.session_cookie_secure = False

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _ensure_database_exists(database_url: str) -> None:
    url = make_url(database_url)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin_engine.dispose()


def _run_migrations() -> None:
    """Build the schema via the real Alembic migrations, not a shortcut.

    Running the same migration history the app/docker-compose use means a
    broken migration fails a test run instead of only surfacing later.
    """
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    _ensure_database_exists(settings.database_url)
    _run_migrations()


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    yield


@pytest.fixture
def fake_object_storage(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStorage:
    fake = FakeObjectStorage()
    monkeypatch.setattr(providers, "get_object_storage", lambda: fake)
    return fake


@pytest.fixture
def fake_embedding_provider(monkeypatch: pytest.MonkeyPatch) -> FakeEmbeddingProvider:
    fake = FakeEmbeddingProvider()
    monkeypatch.setattr(providers, "get_embedding_provider", lambda: fake)
    return fake


@pytest.fixture
def fake_llm_provider(monkeypatch: pytest.MonkeyPatch) -> FakeLLMProvider:
    fake = FakeLLMProvider()
    monkeypatch.setattr(providers, "get_llm_provider", lambda: fake)
    return fake


@pytest.fixture
def client(
    fake_object_storage: FakeObjectStorage,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_llm_provider: FakeLLMProvider,
) -> TestClient:
    return TestClient(app)
