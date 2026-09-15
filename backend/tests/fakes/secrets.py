from app.adapters.secrets import SecretNotFoundError


class FakeSecretManager:
    """In-memory SecretManager — no local file, no real network calls."""

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = dict(secrets or {})

    def get_secret(self, name: str) -> str:
        try:
            return self._secrets[name]
        except KeyError:
            raise SecretNotFoundError(f"No fake secret named {name!r}") from None


__all__ = ["FakeSecretManager", "SecretNotFoundError"]
