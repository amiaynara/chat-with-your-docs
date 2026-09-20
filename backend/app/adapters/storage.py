from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.adapters.retry import PermanentProviderError, TransientProviderError, with_provider_retry


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> str:
        """Store bytes under `key`, returning a storage reference."""
        ...

    def get(self, ref: str) -> bytes:
        """Retrieve bytes previously stored under `ref`."""
        ...

    def delete(self, ref: str) -> None:
        """Delete the object at `ref`. No-op if it doesn't exist."""
        ...


_FAIL_FAST_ERROR_CODES = {
    "AccessDenied",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "NoSuchBucket",
    "NoSuchKey",
}


def _classify_client_error(exc: ClientError) -> Exception:
    code = exc.response.get("Error", {}).get("Code", "")
    if code in _FAIL_FAST_ERROR_CODES:
        return PermanentProviderError(str(exc))
    return TransientProviderError(str(exc))


class S3ObjectStorage:
    """S3-compatible object storage (MinIO locally, real AWS S3 in production).

    The endpoint/credentials are the only production difference — this same
    client works against either without code changes. `endpoint_url`/`access_key`/
    `secret_key` are optional: MinIO needs all three (a custom endpoint, no IAM role
    to fall back on); real AWS S3 needs neither — infra/ (issue #23) grants the ECS
    task role S3 access directly, so boto3's default credential chain resolves it and
    the real AWS S3 endpoint is used automatically. Leave whichever of the three
    unset/empty for that case, rather than passing empty-string credentials, which
    boto3 would treat as literal (invalid) values instead of "use the default chain."
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._bucket = bucket
        client_kwargs: dict[str, str] = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key
        self._client = boto3.client(
            "s3",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 0},
                connect_timeout=timeout_seconds,
                read_timeout=timeout_seconds,
            ),
            **client_kwargs,
        )
        self._ensure_bucket()

    @with_provider_retry
    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except EndpointConnectionError as exc:
            raise TransientProviderError(str(exc)) from exc
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "404":
                self._client.create_bucket(Bucket=self._bucket)
                return
            raise _classify_client_error(exc) from exc

    @with_provider_retry
    def put(self, key: str, data: bytes) -> str:
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        except EndpointConnectionError as exc:
            raise TransientProviderError(str(exc)) from exc
        except ClientError as exc:
            raise _classify_client_error(exc) from exc
        return key

    @with_provider_retry
    def get(self, ref: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=ref)
            return response["Body"].read()
        except EndpointConnectionError as exc:
            raise TransientProviderError(str(exc)) from exc
        except ClientError as exc:
            raise _classify_client_error(exc) from exc

    @with_provider_retry
    def delete(self, ref: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=ref)
        except EndpointConnectionError as exc:
            raise TransientProviderError(str(exc)) from exc
        except ClientError as exc:
            raise _classify_client_error(exc) from exc
