import pytest

from app.place_detail_enrichment_cli import _is_blocked_error as detail_blocked
from app.place_id_linker_cli import _is_blocked_error as linker_blocked


@pytest.mark.parametrize("message", ["HTTP 403", "HTTP 429", "CAPTCHA detected", "BLOCKED by service"])
def test_linker_blocked_errors_are_not_treated_as_item_failures(message):
    assert linker_blocked(RuntimeError(message)) is True


@pytest.mark.parametrize("message", ["HTTP 403", "HTTP 429", "CAPTCHA detected", "BLOCKED by service"])
def test_detail_blocked_errors_are_not_treated_as_item_failures(message):
    assert detail_blocked(RuntimeError(message)) is True
