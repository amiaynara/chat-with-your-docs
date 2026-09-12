import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import (
    models,  # noqa: F401  (registers ORM models on Base.metadata)
    providers,
)
from app.celery_app import celery_app
from app.db import Base, engine
from app.main import app
from tests.fakes.embeddings import FakeEmbeddingProvider
from tests.fakes.llm import FakeLLMProvider
from tests.fakes.storage import FakeObjectStorage

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)


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
