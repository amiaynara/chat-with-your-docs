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
    client works against either without code changes.
    """

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket: str) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 0}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

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
