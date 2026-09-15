"""Tests for the SecretManager adapter (issue #22).

`LocalSecretManager` is pure local-file I/O, covered directly. `_classify_client_error`
is a pure function, tested directly with no marker needed (mirrors
test_storage_adapter.py). `AWSSecretManager`'s error-translation tests need no real (or
mocked) AWS at all — unlike `S3ObjectStorage`, constructing it makes no network call
(no `_ensure_bucket`-style startup check), so monkeypatching `_client.get_secret_value`
after construction is enough.

The round-trip/not-found tests exercise the real `boto3` Secrets Manager code path
(not our own fake) against `moto`'s mocked AWS backend rather than a real AWS account —
the "moto" alternative the ticket calls out — so they're still marked `integration`
(excluded from the default `-m 'not integration'` run — see pyproject.toml) as a
contract test, mirroring test_storage_adapter.py's real-MinIO pattern, but need no
real credentials/network to run.
"""

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from moto import mock_aws

from app.adapters.retry import PermanentProviderError, TransientProviderError
from app.adapters.secrets import (
    AWSSecretManager,
    LocalSecretManager,
    SecretNotFoundError,
    _classify_client_error,
)


def _raising(exc: Exception):
    def _fn(*args, **kwargs):
        raise exc

    return _fn


# --- LocalSecretManager -------------------------------------------------


def test_local_secret_manager_reads_a_value_from_the_fixture_file(tmp_path):
    secrets_file = tmp_path / ".secrets"
    secrets_file.write_text("ANTHROPIC_API_KEY=sk-test-123\nCOHERE_API_KEY=co-test-456\n")

    manager = LocalSecretManager(str(secrets_file))

    assert manager.get_secret("ANTHROPIC_API_KEY") == "sk-test-123"
    assert manager.get_secret("COHERE_API_KEY") == "co-test-456"


def test_local_secret_manager_ignores_blank_lines_and_comments(tmp_path):
    secrets_file = tmp_path / ".secrets"
    secrets_file.write_text("\n# a comment\nANTHROPIC_API_KEY=sk-test-123\n\n")

    manager = LocalSecretManager(str(secrets_file))

    assert manager.get_secret("ANTHROPIC_API_KEY") == "sk-test-123"


def test_local_secret_manager_ignores_a_line_with_no_separator(tmp_path):
    secrets_file = tmp_path / ".secrets"
    secrets_file.write_text("this line has no equals sign\nANTHROPIC_API_KEY=sk-test-123\n")

    manager = LocalSecretManager(str(secrets_file))

    assert manager.get_secret("ANTHROPIC_API_KEY") == "sk-test-123"


def test_local_secret_manager_strips_surrounding_whitespace(tmp_path):
    secrets_file = tmp_path / ".secrets"
    secrets_file.write_text("  ANTHROPIC_API_KEY = sk-test-123  \n")

    manager = LocalSecretManager(str(secrets_file))

    assert manager.get_secret("ANTHROPIC_API_KEY") == "sk-test-123"


def test_local_secret_manager_raises_a_typed_error_for_a_missing_secret(tmp_path):
    secrets_file = tmp_path / ".secrets"
    secrets_file.write_text("ANTHROPIC_API_KEY=sk-test-123\n")

    manager = LocalSecretManager(str(secrets_file))

    with pytest.raises(SecretNotFoundError, match="OPENAI_API_KEY"):
        manager.get_secret("OPENAI_API_KEY")


def test_local_secret_manager_construction_does_not_fail_when_the_file_is_missing(tmp_path):
    missing_file = tmp_path / "does-not-exist"

    manager = LocalSecretManager(str(missing_file))

    with pytest.raises(SecretNotFoundError):
        manager.get_secret("ANYTHING")


# --- AWSSecretManager error classification/translation -------------------
# No real (or mocked) AWS needed: AWSSecretManager's constructor makes no network
# call, so these monkeypatch the underlying boto3 client after construction.


def _make_manager() -> AWSSecretManager:
    return AWSSecretManager(region="us-east-1", timeout_seconds=5.0)


def test_classify_client_error_maps_a_fail_fast_code_to_permanent():
    error = ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetSecretValue")

    assert isinstance(_classify_client_error(error), PermanentProviderError)


def test_classify_client_error_maps_an_unrecognized_code_to_transient():
    error = ClientError({"Error": {"Code": "InternalServiceError"}}, "GetSecretValue")

    assert isinstance(_classify_client_error(error), TransientProviderError)


def test_get_secret_translates_endpoint_connection_error_to_transient():
    manager = _make_manager()
    manager._client.get_secret_value = _raising(EndpointConnectionError(endpoint_url="http://x"))

    with pytest.raises(TransientProviderError):
        manager.get_secret("some-secret")


def test_get_secret_translates_a_client_error_via_classification():
    manager = _make_manager()
    manager._client.get_secret_value = _raising(
        ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetSecretValue")
    )

    with pytest.raises(PermanentProviderError):
        manager.get_secret("some-secret")


def test_get_secret_raises_a_typed_error_for_a_binary_secret():
    manager = _make_manager()
    manager._client.get_secret_value = lambda **kwargs: {"SecretBinary": b"\x00\x01"}

    with pytest.raises(PermanentProviderError, match="binary secrets are not supported"):
        manager.get_secret("some-binary-secret")


def test_get_secret_raises_secret_not_found_when_the_sdk_reports_resource_not_found():
    manager = _make_manager()
    manager._client.get_secret_value = _raising(
        ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetSecretValue")
    )

    with pytest.raises(SecretNotFoundError):
        manager.get_secret("does-not-exist")


# --- AWSSecretManager contract test (real boto3 code path, moto-mocked AWS) ----


@pytest.fixture
def _fake_aws_credentials(monkeypatch):
    # moto intercepts the actual API calls, but boto3 still wants *some*
    # credentials present to build a request — these never reach a real AWS account.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.mark.integration
@mock_aws
def test_get_secret_round_trips_against_a_mocked_aws_secrets_manager(_fake_aws_credentials):
    manager = _make_manager()
    manager._client.create_secret(Name="some-secret", SecretString="hello world")

    assert manager.get_secret("some-secret") == "hello world"


@pytest.mark.integration
@mock_aws
def test_get_secret_raises_secret_not_found_for_a_secret_that_was_never_created(
    _fake_aws_credentials,
):
    manager = _make_manager()

    with pytest.raises(SecretNotFoundError):
        manager.get_secret("never-created")
