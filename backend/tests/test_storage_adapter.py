"""Tests for the real S3ObjectStorage adapter (MinIO locally).

Marked `integration` (excluded from the default `-m 'not integration'` run —
see pyproject.toml) since these need a real, reachable object store: run
with `uv run pytest -m integration`. This is the contract-test layer the
spec (issue #1) calls for — real adapter, real service, no fakes — kept
separate from the fast, hermetic default suite.

`_classify_client_error` itself is a pure function and is tested directly,
with no marker needed.
"""

import uuid

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.adapters.retry import PermanentProviderError, TransientProviderError
from app.adapters.storage import S3ObjectStorage, _classify_client_error
from app.config import settings


def _raising(exc: Exception):
    def _fn(*args, **kwargs):
        raise exc

    return _fn


def _make_storage(bucket: str | None = None) -> S3ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=settings.object_storage_endpoint_url,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        bucket=bucket or f"test-{uuid.uuid4()}",
        timeout_seconds=5.0,
    )


class _FakeBotoClient:
    def head_bucket(self, **kwargs):
        pass


def test_boto_client_omits_endpoint_and_credentials_when_not_provided(monkeypatch):
    """Real AWS S3 in production (infra/, issue #23): no custom endpoint, and the ECS
    task's IAM role — not static keys — supplies credentials via boto3's default
    chain. Passing empty-string credentials would be treated as literal (invalid)
    values rather than "fall back to the chain", so the client call must omit the
    kwargs entirely, not just pass them empty.
    """
    captured = {}

    def fake_client(service_name, **kwargs):
        captured.update(kwargs)
        return _FakeBotoClient()

    monkeypatch.setattr("app.adapters.storage.boto3.client", fake_client)

    S3ObjectStorage(bucket="my-bucket")

    assert "endpoint_url" not in captured
    assert "aws_access_key_id" not in captured
    assert "aws_secret_access_key" not in captured


def test_boto_client_includes_endpoint_and_credentials_when_provided(monkeypatch):
    captured = {}

    def fake_client(service_name, **kwargs):
        captured.update(kwargs)
        return _FakeBotoClient()

    monkeypatch.setattr("app.adapters.storage.boto3.client", fake_client)

    S3ObjectStorage(
        bucket="my-bucket",
        endpoint_url="http://localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
    )

    assert captured["endpoint_url"] == "http://localhost:9000"
    assert captured["aws_access_key_id"] == "minioadmin"
    assert captured["aws_secret_access_key"] == "minioadmin"


def test_classify_client_error_maps_a_fail_fast_code_to_permanent():
    error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    assert isinstance(_classify_client_error(error), PermanentProviderError)


def test_classify_client_error_maps_an_unrecognized_code_to_transient():
    error = ClientError({"Error": {"Code": "InternalError"}}, "GetObject")

    assert isinstance(_classify_client_error(error), TransientProviderError)


@pytest.mark.integration
def test_put_get_delete_round_trip_against_real_minio():
    storage = _make_storage()

    storage.put("some/key.txt", b"hello world")
    assert storage.get("some/key.txt") == b"hello world"

    storage.delete("some/key.txt")
    with pytest.raises(PermanentProviderError):
        storage.get("some/key.txt")


@pytest.mark.integration
def test_ensure_bucket_creates_a_missing_bucket_then_is_a_no_op_once_it_exists():
    bucket = f"test-{uuid.uuid4()}"

    _make_storage(bucket)  # bucket doesn't exist yet: creates it
    _make_storage(bucket)  # bucket exists now: head_bucket succeeds, no-op


@pytest.mark.integration
def test_put_translates_endpoint_connection_error_to_transient():
    storage = _make_storage()
    storage._client.put_object = _raising(EndpointConnectionError(endpoint_url="http://x"))

    with pytest.raises(TransientProviderError):
        storage.put("key", b"data")


@pytest.mark.integration
def test_put_translates_a_client_error_via_classification():
    storage = _make_storage()
    storage._client.put_object = _raising(
        ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
    )

    with pytest.raises(PermanentProviderError):
        storage.put("key", b"data")


@pytest.mark.integration
def test_get_translates_endpoint_connection_error_to_transient():
    storage = _make_storage()
    storage._client.get_object = _raising(EndpointConnectionError(endpoint_url="http://x"))

    with pytest.raises(TransientProviderError):
        storage.get("key")


@pytest.mark.integration
def test_get_translates_a_client_error_via_classification():
    storage = _make_storage()
    storage._client.get_object = _raising(
        ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
    )

    with pytest.raises(PermanentProviderError):
        storage.get("key")


@pytest.mark.integration
def test_delete_translates_endpoint_connection_error_to_transient():
    storage = _make_storage()
    storage._client.delete_object = _raising(EndpointConnectionError(endpoint_url="http://x"))

    with pytest.raises(TransientProviderError):
        storage.delete("key")


@pytest.mark.integration
def test_delete_translates_a_client_error_via_classification():
    storage = _make_storage()
    storage._client.delete_object = _raising(
        ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")
    )

    with pytest.raises(PermanentProviderError):
        storage.delete("key")


@pytest.mark.integration
def test_ensure_bucket_translates_endpoint_connection_error_to_transient():
    storage = _make_storage()
    storage._client.head_bucket = _raising(EndpointConnectionError(endpoint_url="http://x"))

    with pytest.raises(TransientProviderError):
        storage._ensure_bucket()


@pytest.mark.integration
def test_ensure_bucket_reraises_a_non_404_client_error_classified():
    storage = _make_storage()
    storage._client.head_bucket = _raising(
        ClientError({"Error": {"Code": "AccessDenied"}}, "HeadBucket")
    )

    with pytest.raises(PermanentProviderError):
        storage._ensure_bucket()
