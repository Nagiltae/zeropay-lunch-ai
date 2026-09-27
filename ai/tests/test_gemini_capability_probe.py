from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.gemini_capability_probe import GeminiCapabilityProbe


def _menu(menu_id: int) -> dict:
    return {"id": menu_id, "name": f"menu-{menu_id}", "priceValue": 9000}


def _classification(menu: dict, eligibility="UNKNOWN", flags=None) -> dict:
    return {
        "menuId": menu["id"],
        "budgetEligibility": eligibility,
        "flags": flags or [],
    }


def _probe(**overrides):
    args = {
        "interval_seconds": 5,
        "sleep": lambda _: None,
        "monotonic": iter(range(1000)).__next__,
        "wall_clock": lambda: datetime(2026, 9, 26, tzinfo=UTC),
    }
    args.update(overrides)
    return GeminiCapabilityProbe(**args)


def _run(probe, *, plain_call=None, structured_call=None, menu_call=None):
    one = [_menu(1)]
    three = [_menu(2), _menu(3), _menu(4)]
    twelve = [_menu(value) for value in range(10, 22)]
    if plain_call is None:

        def plain_call():
            return SimpleNamespace(text="OK")

    if structured_call is None:

        def structured_call():
            return SimpleNamespace(text='{"status":"OK"}')

    if menu_call is None:

        def menu_call(rows):
            return [_classification(row) for row in rows], {}

    return probe.run(
        plain_call=plain_call,
        structured_call=structured_call,
        menu_call=menu_call,
        menus_single=one,
        menus_three=three,
        menus_twelve=twelve,
        expected_single={"budgetEligibility": "UNKNOWN", "flags": []},
        expected_three={row["id"]: {"budgetEligibility": "UNKNOWN", "flags": []} for row in three},
        expected_twelve={
            row["id"]: {"budgetEligibility": "UNKNOWN", "flags": []} for row in twelve
        },
        input_bytes=lambda rows: len(rows) * 11,
    )


def test_all_stages_progress_in_order_and_record_payload_metrics():
    calls = []

    def plain():
        calls.append("1")
        return SimpleNamespace(text="OK")

    def structured():
        calls.append("2")
        return SimpleNamespace(text='{"status":"OK"}')

    def menus(rows):
        calls.append(str(len(rows)))
        return [_classification(row) for row in rows], {}

    result = _run(_probe(), plain_call=plain, structured_call=structured, menu_call=menus)
    assert result["probeStatus"] == "PASS"
    assert calls == ["1", "1", "1", "2", "2", "1", "3", "12"]
    assert result["apiRequestCount"] == 8
    assert [result["stages"][key]["status"] for key in ("1", "2", "3", "4", "5")] == [
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
    ]
    assert result["stages"]["5"]["inputBytes"] == 132
    assert result["stages"]["5"]["menuCount"] == 12


@pytest.mark.parametrize(
    ("status", "expected"),
    [(400, "CLIENT_ERROR"), (403, "ACCESS_RESTRICTED"), (429, "RATE_LIMITED")],
)
def test_hard_provider_errors_stop_all_later_stages_without_retry(status, expected):
    ApiError = type("ApiError", (Exception,), {})

    calls = []

    def plain():
        calls.append("plain")
        error = ApiError("do not persist this raw message")
        error.code = status
        error.status = "SAFE_STATUS"
        raise error

    result = _run(_probe(), plain_call=plain)
    assert result["stopReason"] == expected
    assert result["apiRequestCount"] == 1
    assert calls == ["plain"]
    assert result["requestEvents"][0]["retryAfterPresent"] is False
    assert "do not persist" not in str(result)


def test_plain_text_gate_requires_two_of_three_before_structured_stage():
    calls = {"plain": 0, "structured": 0}

    def plain():
        calls["plain"] += 1
        return SimpleNamespace(text="not OK")

    def structured():
        calls["structured"] += 1
        return SimpleNamespace(text='{"status":"OK"}')

    result = _run(_probe(), plain_call=plain, structured_call=structured)
    assert result["probeStatus"] == "PROVIDER_UNAVAILABLE_MINIMAL_REQUEST"
    assert calls == {"plain": 3, "structured": 0}
    assert result["stages"]["2"]["status"] == "NOT_RUN"


def test_503_has_exactly_one_retry_and_safe_event_metadata():
    class ApiError(Exception):
        code = 503
        status = "UNAVAILABLE"
        response = SimpleNamespace(headers={"Retry-After": "1"})

    count = 0

    def plain():
        nonlocal count
        count += 1
        if count == 1:
            raise ApiError("sensitive raw provider detail")
        return SimpleNamespace(text="OK")

    result = _run(_probe(), plain_call=plain)
    assert count == 4  # one retry plus the remaining two independent checks
    assert result["stages"]["1"]["retryCount"] == 1
    assert result["requestEvents"][0]["statusCode"] == 503
    assert result["requestEvents"][0]["retryAfterPresent"] is True
    assert "sensitive raw" not in str(result)


def test_structured_output_failure_stops_classifier_stages():
    calls = {"menu": 0}

    def structured():
        return SimpleNamespace(text='{"status":"NOT_OK"}')

    def menus(rows):
        calls["menu"] += 1
        return [_classification(row) for row in rows], {}

    result = _run(_probe(), structured_call=structured, menu_call=menus)
    assert result["probeStatus"] == "STRUCTURED_OUTPUT_UNSTABLE"
    assert result["stages"]["2"]["status"] == "FAIL"
    assert calls["menu"] == 0


def test_429_after_a_5xx_retry_stops_before_next_independent_request():
    class ApiError(Exception):
        status = "RESOURCE_EXHAUSTED"

        def __init__(self, code):
            self.code = code

    calls = {"plain": 0, "structured": 0, "menu": 0}

    def plain():
        calls["plain"] += 1
        return SimpleNamespace(text="OK")

    def structured():
        calls["structured"] += 1
        raise ApiError(503 if calls["structured"] == 1 else 429)

    def menus(rows):
        calls["menu"] += 1
        return [_classification(row) for row in rows], {}

    result = _run(_probe(), plain_call=plain, structured_call=structured, menu_call=menus)
    assert result["probeStatus"] == "RATE_LIMITED"
    assert result["apiRequestCount"] == 5
    assert result["retryCount"] == 1
    assert result["statusCounts"]["429"] == 1
    assert calls == {"plain": 3, "structured": 2, "menu": 0}
