"""Small staged Gemini capability probe with safe diagnostics and bounded retries."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from app.menu_budget_classifier import RequestPacer


class ProbeStop(Exception):
    def __init__(self, reason: str, status_code: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "code", None) or getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_diagnostics(error: Exception) -> dict:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    try:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
    except (AttributeError, TypeError):
        retry_after = None
    status = getattr(error, "status", None)
    status_code = _status_code(error)
    lowered = status.lower() if isinstance(status, str) else ""
    if status_code == 429 or "rate" in lowered:
        category = "rate_limit"
    elif status_code == 403:
        category = "access_restriction"
    elif status_code == 400:
        category = "client_request"
    elif status_code is not None and 500 <= status_code <= 599:
        category = "provider_5xx"
    elif "timeout" in error.__class__.__name__.lower():
        category = "timeout"
    else:
        category = "network_transport"
    return {
        "statusCode": status_code,
        "apiStatus": status if isinstance(status, str) else None,
        "retryAfterPresent": retry_after is not None,
        "safeErrorCategory": category,
    }


class GeminiCapabilityProbe:
    """Executes only explicitly supplied staged calls; all provider calls are serial."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ):
        self._sleep = sleep
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._pacer = RequestPacer(interval_seconds, sleep=sleep, monotonic=monotonic)
        self._ordinal = 0
        self._stop_reason: str | None = None
        self._stages: dict[str, dict] = {}
        self._events: list[dict] = []

    def _invoke(
        self,
        *,
        stage: str,
        menu_count: int,
        input_bytes: int,
        call: Callable,
        validate: Callable,
    ) -> tuple[bool, object | None, str | None]:
        stage_result = self._stages[stage]
        stage_result["independentRequests"] += 1
        for attempt in (1, 2):
            self._pacer.before_request()
            self._ordinal += 1
            started_at = self._wall_clock().isoformat()
            started = self._monotonic()
            event = {
                "stage": stage,
                "requestOrdinal": self._ordinal,
                "timestamp": started_at,
                "attempt": attempt,
                "menuCount": menu_count,
                "inputBytes": input_bytes,
            }
            self._events.append(event)
            stage_result["attempts"] += 1
            try:
                response = call()
            except Exception as error:  # SDK transport error types vary by version.
                diagnostics = _safe_diagnostics(error)
                event.update(diagnostics)
                event["latencySeconds"] = round(self._monotonic() - started, 3)
                event["outcome"] = "HTTP_ERROR" if diagnostics["statusCode"] else "TRANSPORT_ERROR"
                status = diagnostics["statusCode"]
                if status in (400, 403, 429):
                    self._stop_reason = {
                        400: "CLIENT_ERROR",
                        403: "ACCESS_RESTRICTED",
                        429: "RATE_LIMITED",
                    }[status]
                    return False, None, self._stop_reason
                transient = (
                    (status is not None and 500 <= status <= 599)
                    or error.__class__.__module__.startswith(("httpx", "httpcore"))
                    or isinstance(error, (TimeoutError, ConnectionError, OSError))
                )
                if attempt == 1 and transient:
                    stage_result["retryCount"] += 1
                    self._sleep(2)
                    continue
                return False, None, "PROVIDER_ERROR"

            stage_result["apiResponses"] += 1
            event["latencySeconds"] = round(self._monotonic() - started, 3)
            try:
                valid, safe_value = validate(response)
            except Exception:
                valid, safe_value = False, None
            event["outcome"] = "RESPONSE_VALID" if valid else "RESPONSE_INVALID"
            if valid:
                stage_result["validResponses"] += 1
                return True, safe_value, None
            stage_result["invalidResponses"] += 1
            return False, safe_value, "RESPONSE_INVALID"
        return False, None, "PROVIDER_ERROR"

    def run(
        self,
        *,
        plain_call: Callable,
        structured_call: Callable,
        menu_call: Callable[[list[dict]], tuple[list[dict], dict]],
        menus_single: list[dict],
        menus_three: list[dict],
        menus_twelve: list[dict],
        expected_single: dict,
        expected_three: dict[int, dict],
        expected_twelve: dict[int, dict],
        input_bytes: Callable[[list[dict]], int],
        structured_input_bytes: int = len(b'{"status":"OK"}'),
    ) -> dict:
        self._stages = {
            str(index): {
                "requestType": label,
                "menuCount": count,
                "inputBytes": size,
                "independentRequests": 0,
                "attempts": 0,
                "apiResponses": 0,
                "validResponses": 0,
                "invalidResponses": 0,
                "retryCount": 0,
                "status": "NOT_RUN",
                "latencySeconds": [],
                "outputs": [],
            }
            for index, label, count, size in [
                ("1", "plain_text", 0, len(b"Reply with exactly: OK")),
                ("2", "structured_minimal", 0, structured_input_bytes),
                ("3", "menu_classifier", 1, input_bytes(menus_single)),
                ("4", "menu_classifier", 3, input_bytes(menus_three)),
                ("5", "menu_classifier", 12, input_bytes(menus_twelve)),
            ]
        }

        plain_successes = 0
        for _ in range(3):
            ok, value, error = self._invoke(
                stage="1",
                menu_count=0,
                input_bytes=len(b"Reply with exactly: OK"),
                call=plain_call,
                validate=lambda response: (
                    isinstance(getattr(response, "text", None), str)
                    and response.text.strip() == "OK",
                    {"exactOk": getattr(response, "text", "").strip() == "OK"},
                ),
            )
            plain_successes += int(ok)
            if value is not None:
                self._stages["1"]["outputs"].append(value)
            if error in {"RATE_LIMITED", "ACCESS_RESTRICTED", "CLIENT_ERROR"}:
                break
        self._stages["1"]["status"] = "PASS" if plain_successes >= 2 else "FAIL"
        self._stages["1"]["successes"] = plain_successes

        if self._stop_reason is None and self._stages["1"]["status"] == "PASS":
            for _ in range(2):
                ok, value, error = self._invoke(
                    stage="2",
                    menu_count=0,
                    input_bytes=structured_input_bytes,
                    call=structured_call,
                    validate=lambda response: self._validate_structured_minimal(response),
                )
                if value is not None:
                    self._stages["2"]["outputs"].append(value)
                if error in {"RATE_LIMITED", "ACCESS_RESTRICTED", "CLIENT_ERROR"}:
                    break
            self._stages["2"]["status"] = (
                "PASS"
                if self._stages["2"]["validResponses"] == 2
                and self._stages["2"]["independentRequests"] == 2
                else "FAIL"
            )

        for stage, menus, expected in (
            ("3", menus_single, {int(menus_single[0]["id"]): expected_single}),
            ("4", menus_three, expected_three),
            ("5", menus_twelve, expected_twelve),
        ):
            if (
                self._stop_reason is not None
                or self._stages.get(str(int(stage) - 1), {}).get("status") != "PASS"
            ):
                break
            ok, value, error = self._invoke(
                stage=stage,
                menu_count=len(menus),
                input_bytes=input_bytes(menus),
                call=lambda selected=menus: menu_call(selected),
                validate=lambda response, selected=menus, expected_rows=expected: (
                    self._validate_menu_response(response, selected, expected_rows)
                ),
            )
            if value is not None:
                self._stages[stage]["outputs"].append(value)
            self._stages[stage]["status"] = "PASS" if ok else "FAIL"
            if error in {"RATE_LIMITED", "ACCESS_RESTRICTED", "CLIENT_ERROR"}:
                break

        if self._stop_reason == "RATE_LIMITED":
            overall = "RATE_LIMITED"
        elif self._stop_reason == "ACCESS_RESTRICTED":
            overall = "ACCESS_RESTRICTED"
        elif self._stop_reason == "CLIENT_ERROR":
            overall = "CLIENT_REQUEST_ERROR"
        elif self._stages["1"]["status"] != "PASS":
            overall = "PROVIDER_UNAVAILABLE_MINIMAL_REQUEST"
        elif self._stages["2"].get("status") != "PASS":
            overall = "STRUCTURED_OUTPUT_UNSTABLE"
        elif self._stages["3"].get("status") != "PASS":
            overall = "MENU_CLASSIFIER_REQUEST_ISSUE"
        elif self._stages["4"].get("status") != "PASS":
            overall = "MENU_CLASSIFIER_REQUEST_ISSUE"
        elif self._stages["5"].get("status") != "PASS":
            overall = "PAYLOAD_OR_COMPLEXITY_SENSITIVE"
        else:
            overall = "PASS"

        for stage in self._stages.values():
            latencies = [
                event["latencySeconds"]
                for event in self._events
                if event["stage"]
                == next(key for key, value in self._stages.items() if value is stage)
            ]
            stage["averageLatencySeconds"] = (
                round(sum(latencies) / len(latencies), 3) if latencies else None
            )
            stage.pop("latencySeconds", None)
        return {
            "probeStatus": overall,
            "stopReason": self._stop_reason,
            "stages": self._stages,
            "requestEvents": self._events,
            "apiRequestCount": self._ordinal,
            "retryCount": sum(stage["retryCount"] for stage in self._stages.values()),
            "statusCounts": {
                str(code): sum(event.get("statusCode") == code for event in self._events)
                for code in (400, 403, 429)
            }
            | {
                "5xx": sum(
                    isinstance(event.get("statusCode"), int) and 500 <= event["statusCode"] <= 599
                    for event in self._events
                ),
                "network": sum(event.get("outcome") == "TRANSPORT_ERROR" for event in self._events),
            },
            "databaseWrites": 0,
            "qdrantWrites": 0,
            "springImporter": False,
            "runtimeUsage": False,
        }

    @staticmethod
    def _validate_structured_minimal(response) -> tuple[bool, dict | None]:
        import json

        raw = getattr(response, "text", None)
        if not isinstance(raw, str):
            return False, None
        parsed = json.loads(raw)
        valid = isinstance(parsed, dict) and parsed == {"status": "OK"}
        return valid, {"status": parsed.get("status")} if isinstance(parsed, dict) else None

    @staticmethod
    def _validate_menu_response(
        response: tuple[list[dict], dict], menus: list[dict], expected: dict[int, dict]
    ) -> tuple[bool, dict | None]:
        from app.menu_budget_classifier import ClassificationBatchError, merge_chunk_result

        classifications, usage = response
        merged = merge_chunk_result(menus, classifications)
        expected_ids = {int(menu["id"]) for menu in menus}
        actual_ids = {int(row["menuId"]) for row in merged}
        if actual_ids != expected_ids:
            raise ClassificationBatchError("menu ID set mismatch")
        omitted_ids = {
            menu_id
            for menu_id in expected_ids
            if not any(int(row["menuId"]) == menu_id for row in classifications)
        }
        by_id = {int(row["menuId"]): row for row in merged}
        fixture_matches = {
            str(menu_id): (
                by_id[menu_id]["budgetEligibility"] == expected_row["budgetEligibility"]
                and set(expected_row["flags"]).issubset(set(by_id[menu_id]["flags"]))
            )
            for menu_id, expected_row in expected.items()
            if menu_id in by_id
        }
        return True, {
            "classifications": merged,
            "omittedMenuIds": sorted(omitted_ids),
            "fixtureMatches": fixture_matches,
            "usage": usage,
        }
