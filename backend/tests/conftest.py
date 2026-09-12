import pytest
from fastapi.testclient import TestClient

from app.celery_app import celery_app
from app.main import app

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
