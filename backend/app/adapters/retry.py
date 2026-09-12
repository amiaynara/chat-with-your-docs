"""Shared retry/timeout policy for all external provider adapters.

Transient failures (timeouts, rate limits, 5xx) are retried with bounded
exponential backoff. Invalid-request/auth errors (4xx other than 429) are
never retried — they fail immediately since retrying can't fix them.
"""

from collections.abc import Callable
from typing import ParamSpec, TypeVar

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


class TransientProviderError(Exception):
    """Raised by an adapter for a retryable failure (timeout, 429, 5xx)."""


class PermanentProviderError(Exception):
    """Raised by an adapter for a non-retryable failure (400/401/403)."""


P = ParamSpec("P")
T = TypeVar("T")


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, TransientProviderError)


def with_provider_retry(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator applying bounded exponential-backoff retry to transient errors only."""
    return retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )(func)


def classify_provider_call(
    call: Callable[[], T],
    *,
    transient_exceptions: tuple[type[BaseException], ...],
    status_error_type: type[BaseException] | None = None,
) -> T:
    """Run `call`, translating SDK-specific exceptions to Transient/PermanentProviderError.

    `transient_exceptions` (e.g. an SDK's RateLimitError/timeout/connection-error
    types) are always treated as transient. `status_error_type` (e.g. an SDK's
    generic APIStatusError) is classified by its `.status_code`: 429/5xx is
    transient, everything else (bad request, auth) is permanent.

    Shared by every provider adapter so the same policy — not a per-adapter
    reimplementation of it — decides what gets retried.
    """
    try:
        return call()
    except transient_exceptions as exc:
        raise TransientProviderError(str(exc)) from exc
    except BaseException as exc:
        if status_error_type is not None and isinstance(exc, status_error_type):
            status_code = getattr(exc, "status_code", 500)
            if status_code == 429 or status_code >= 500:
                raise TransientProviderError(str(exc)) from exc
            raise PermanentProviderError(str(exc)) from exc
        raise
