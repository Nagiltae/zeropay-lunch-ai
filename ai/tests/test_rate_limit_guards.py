import pytest

from app.place_detail_enrichment_cli import _is_blocked_error as detail_blocked
from app.place_id_linker_cli import _is_blocked_error as linker_blocked
from app.place_request_limiter import TransientRetryPolicy
from app.provider_entity_resolution_cli import _blocked_provider_error


@pytest.mark.parametrize(
    "message", ["HTTP 403", "HTTP 429", "CAPTCHA detected", "BLOCKED by service"]
)
def test_linker_blocked_errors_are_not_treated_as_item_failures(message):
    assert linker_blocked(RuntimeError(message)) is True


@pytest.mark.parametrize(
    "message", ["HTTP 403", "HTTP 429", "CAPTCHA detected", "BLOCKED by service"]
)
def test_detail_blocked_errors_are_not_treated_as_item_failures(message):
    assert detail_blocked(RuntimeError(message)) is True


def test_transient_retry_is_opt_in_bounded_and_never_for_block(monkeypatch):
    monkeypatch.delenv("BATCH_TRANSIENT_MAX_RETRIES", raising=False)
    assert TransientRetryPolicy.from_env().max_retries == 0
    monkeypatch.setenv("BATCH_TRANSIENT_MAX_RETRIES", "99")
    monkeypatch.setenv("BATCH_TRANSIENT_RETRY_BACKOFF_SECONDS", "3")
    policy = TransientRetryPolicy.from_env()
    assert policy.max_retries == 2
    assert policy.delay(0) == 3
    assert policy.delay(1) == 6
    assert policy.is_retryable(TimeoutError("timeout"))
    assert not policy.is_retryable(RuntimeError("BLOCKED: HTTP 429"))
    assert not policy.is_retryable(ValueError("bad parser"))


def test_official_provider_block_is_detected_before_csv_persistence():
    assert _blocked_provider_error({"kakao_error": "HTTP_429", "naver_error": ""})
    assert _blocked_provider_error({"kakao_error": "", "naver_error": "HTTP_403"})
    assert _blocked_provider_error({"kakao_error": "", "naver_error": "NETWORK_ERROR"}) is None
