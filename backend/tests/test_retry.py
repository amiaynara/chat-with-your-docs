import pytest

from app.adapters.retry import (
    PermanentProviderError,
    TransientProviderError,
    _is_transient,
    classify_provider_call,
    with_provider_retry,
)


class _RateLimited(Exception):
    pass


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _CodeError(Exception):
    """Mimics google-genai's APIError, which exposes `.code` instead of `.status_code`."""

    def __init__(self, code: int) -> None:
        super().__init__(f"code {code}")
        self.code = code


def test_classify_provider_call_returns_the_call_result_on_success():
    assert classify_provider_call(lambda: 42, transient_exceptions=()) == 42


def test_classify_provider_call_maps_a_transient_exception_type():
    def _boom():
        raise _RateLimited("slow down")

    with pytest.raises(TransientProviderError):
        classify_provider_call(_boom, transient_exceptions=(_RateLimited,))


def test_classify_provider_call_maps_a_5xx_status_error_to_transient():
    def _boom():
        raise _StatusError(500)

    with pytest.raises(TransientProviderError):
        classify_provider_call(_boom, transient_exceptions=(), status_error_type=_StatusError)


def test_classify_provider_call_maps_a_429_status_error_to_transient():
    def _boom():
        raise _StatusError(429)

    with pytest.raises(TransientProviderError):
        classify_provider_call(_boom, transient_exceptions=(), status_error_type=_StatusError)


def test_classify_provider_call_maps_a_4xx_status_error_to_permanent():
    def _boom():
        raise _StatusError(400)

    with pytest.raises(PermanentProviderError):
        classify_provider_call(_boom, transient_exceptions=(), status_error_type=_StatusError)


def test_classify_provider_call_reads_a_custom_status_code_attribute():
    def _boom():
        raise _CodeError(500)

    with pytest.raises(TransientProviderError):
        classify_provider_call(
            _boom,
            transient_exceptions=(),
            status_error_type=_CodeError,
            status_code_attr="code",
        )


def test_classify_provider_call_reraises_an_unrecognized_exception():
    def _boom():
        raise ValueError("something else entirely")

    with pytest.raises(ValueError, match="something else entirely"):
        classify_provider_call(_boom, transient_exceptions=(), status_error_type=_StatusError)


def test_is_transient_distinguishes_error_types():
    assert _is_transient(TransientProviderError("x")) is True
    assert _is_transient(PermanentProviderError("x")) is False


def test_with_provider_retry_does_not_retry_a_permanent_error():
    calls = {"count": 0}

    @with_provider_retry
    def _boom():
        calls["count"] += 1
        raise PermanentProviderError("bad request")

    with pytest.raises(PermanentProviderError):
        _boom()

    assert calls["count"] == 1


def test_with_provider_retry_retries_a_transient_error_then_gives_up():
    calls = {"count": 0}

    @with_provider_retry
    def _boom():
        calls["count"] += 1
        raise TransientProviderError("still down")

    with pytest.raises(TransientProviderError):
        _boom()

    assert calls["count"] == 4  # stop_after_attempt(4)
