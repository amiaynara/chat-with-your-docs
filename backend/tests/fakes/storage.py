from app.adapters.retry import PermanentProviderError, TransientProviderError


class FakeObjectStorage:
    """In-memory ObjectStorage — no real network calls."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.fail_next_put_with: Exception | None = None

    def put(self, key: str, data: bytes) -> str:
        if self.fail_next_put_with is not None:
            exc, self.fail_next_put_with = self.fail_next_put_with, None
            raise exc
        self._objects[key] = data
        return key

    def get(self, ref: str) -> bytes:
        if ref not in self._objects:
            raise PermanentProviderError(f"No such object: {ref}")
        return self._objects[ref]

    def delete(self, ref: str) -> None:
        self._objects.pop(ref, None)


__all__ = ["FakeObjectStorage", "PermanentProviderError", "TransientProviderError"]
