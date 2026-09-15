from pathlib import Path
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.adapters.retry import PermanentProviderError, TransientProviderError, with_provider_retry


class SecretNotFoundError(Exception):
    """Raised when a requested secret has no resolvable value — missing from the
    local file, or absent in the remote secret store. Callers get a clear, typed
    failure instead of `None`/`""`, which would silently propagate as an invalid
    credential.
    """


class SecretManager(Protocol):
    def get_secret(self, name: str) -> str:
        """Return the value of the secret named `name`.

        Raises SecretNotFoundError if no value is available for `name`.
        """
        ...


class LocalSecretManager:
    """Reads secrets from a local, gitignored `KEY=value`-per-line file.

    Distinct from pydantic-settings' own `.env`/environment loading in
    app/config.py — this is an explicit, adapter-owned read of a file path, giving
    secret *retrieval* the same seam the app's other external dependencies already
    have (see docs/secrets.md for how the two relate). Zero-setup by design: a
    missing file is not an error at construction (mirrors how this app runs fully
    offline/key-free wherever possible, e.g. EMBEDDING_PROVIDER=local's default) —
    only asking for a secret that was never defined raises.
    """

    def __init__(self, file_path: str) -> None:
        self._secrets = self._load(file_path)

    @staticmethod
    def _load(file_path: str) -> dict[str, str]:
        path = Path(file_path)
        if not path.exists():
            return {}
        secrets: dict[str, str] = {}
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                continue
            secrets[key.strip()] = value.strip()
        return secrets

    def get_secret(self, name: str) -> str:
        try:
            return self._secrets[name]
        except KeyError:
            raise SecretNotFoundError(f"No local secret named {name!r}") from None


_FAIL_FAST_ERROR_CODES = {
    "AccessDeniedException",
    "InvalidRequestException",
    "InvalidParameterException",
    "DecryptionFailure",
}


def _classify_client_error(exc: ClientError) -> Exception:
    code = exc.response.get("Error", {}).get("Code", "")
    if code in _FAIL_FAST_ERROR_CODES:
        return PermanentProviderError(str(exc))
    return TransientProviderError(str(exc))


class AWSSecretManager:
    """Reads secrets from AWS Secrets Manager via boto3, mirroring
    S3ObjectStorage's retry/timeout conventions (app/adapters/storage.py).

    Unlike S3ObjectStorage, this adapter takes no access_key/secret_key —
    credentials come from boto3's normal resolution chain (an IAM role in the AWS
    deployment target described in docs/architecture.md; ~/.aws/* or env vars for
    local use against a real AWS account), since secret *retrieval* is exactly the
    kind of credential boto3's chain exists to keep out of application config.
    """

    def __init__(self, region: str, timeout_seconds: float = 30.0) -> None:
        self._client = boto3.client(
            "secretsmanager",
            region_name=region,
            config=Config(
                retries={"max_attempts": 0},
                connect_timeout=timeout_seconds,
                read_timeout=timeout_seconds,
            ),
        )

    @with_provider_retry
    def get_secret(self, name: str) -> str:
        try:
            response = self._client.get_secret_value(SecretId=name)
        except EndpointConnectionError as exc:
            raise TransientProviderError(str(exc)) from exc
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                raise SecretNotFoundError(
                    f"No secret named {name!r} in AWS Secrets Manager"
                ) from exc
            raise _classify_client_error(exc) from exc
        if "SecretString" not in response:
            raise PermanentProviderError(
                f"Secret {name!r} in AWS Secrets Manager has no SecretString value "
                "(binary secrets are not supported)"
            )
        return response["SecretString"]
