"""Offline, structured classification of whether a stored menu price is a meal budget basis."""

from __future__ import annotations

import json
import os
import time
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MODEL_DEFAULT = "gemini-3.8-flash"
POLICY_VERSION = "menu-budget-classification-v2"
PROMPT_VERSION = "menu-budget-classification-v2-prompt-1"
CHUNK_SIZE = 12
TIMEOUT_MS = 45_000
REQUEST_INTERVAL_DEFAULT_SECONDS = 3.0
ALLOWED_FLAGS = {"SIDE", "DRINK", "ALCOHOL", "MULTI_PERSON", "COURSE", "WEIGHT_BASED"}


class BudgetEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class MenuBudgetFlag(StrEnum):
    SIDE = "SIDE"
    DRINK = "DRINK"
    ALCOHOL = "ALCOHOL"
    MULTI_PERSON = "MULTI_PERSON"
    COURSE = "COURSE"
    WEIGHT_BASED = "WEIGHT_BASED"


class MenuClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    menuId: int
    budgetEligibility: BudgetEligibility
    flags: list[MenuBudgetFlag] = Field(max_length=6)


class MenuClassificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classifications: list[MenuClassification]


class MenuBudgetClassifier(Protocol):
    provider: str
    model: str

    def classify(self, menus: list[dict]) -> tuple[list[dict], dict]: ...


class ClassificationBatchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        retries: int = 0,
        status_code=None,
        diagnostics: dict | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.retries = retries
        self.status_code = status_code
        self.diagnostics = diagnostics or {}


class RequestPacer:
    """Serialize provider calls and enforce a minimum interval between their starts."""

    def __init__(
        self,
        interval_seconds: float,
        *,
        sleep=time.sleep,
        monotonic=time.monotonic,
        elapsed_since_last_request: float | None = None,
    ):
        if interval_seconds < 0:
            raise ValueError("request interval must be non-negative")
        self.interval_seconds = interval_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_started: float | None = None
        if elapsed_since_last_request is not None:
            self._last_started = monotonic() - max(0.0, elapsed_since_last_request)

    def before_request(self) -> float:
        now = self._monotonic()
        waited = 0.0
        if self._last_started is not None:
            waited = max(0.0, self.interval_seconds - (now - self._last_started))
            if waited:
                self._sleep(waited)
        self._last_started = self._monotonic()
        return waited


def _safe_error_diagnostics(error: Exception) -> dict:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = None
    try:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
    except (AttributeError, TypeError):
        pass
    status = getattr(error, "status", None)
    status = status if isinstance(status, str) else None
    status_code = getattr(error, "code", None) or getattr(error, "status_code", None)
    category = "schema_validation" if isinstance(error, ClassificationBatchError) else "network"
    lowered = status.lower() if status else ""
    if "quota" in lowered:
        category = "quota"
    elif "rate" in lowered or status_code == 429:
        category = "rate_limit"
    elif status_code == 403:
        category = "access_restriction"
    elif isinstance(status_code, int) and 500 <= status_code <= 599:
        category = "provider_5xx"
    elif "timeout" in error.__class__.__name__.lower():
        category = "timeout"
    return {
        "apiStatus": status,
        "retryAfterPresent": retry_after is not None,
        "safeErrorCategory": category,
    }


class GeminiMenuBudgetClassifier:
    provider = "GEMINI"

    def __init__(self, *, api_key: str, model: str = MODEL_DEFAULT, client=None):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        if not model:
            raise ValueError("GEMINI_MODEL must not be empty")
        self.model = model
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=TIMEOUT_MS,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        self._client = client

    def classify(self, menus: list[dict]) -> tuple[list[dict], dict]:
        from google.genai import types

        prompt = build_menu_classification_prompt(menus)
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MenuBudgetResponseSchema,
                temperature=0,
            ),
        )
        if not response.text:
            raise ClassificationBatchError("empty structured response")
        try:
            parsed = MenuClassificationResponse.model_validate_json(response.text)
        except ValidationError as error:
            raise ClassificationBatchError("invalid structured response") from error
        usage = getattr(response, "usage_metadata", None)
        usage_values = {}
        if usage is not None:
            for field in ("prompt_token_count", "candidates_token_count", "total_token_count"):
                value = getattr(usage, field, None)
                if value is not None:
                    usage_values[field] = value
        return [item.model_dump(mode="json") for item in parsed.classifications], usage_values


def build_menu_classification_prompt(menus: list[dict]) -> str:
    """Build the existing frozen classifier prompt, shared with probe byte accounting."""
    payload = [
        {
            "menuId": int(menu["id"]),
            "name": menu["name"],
            "description": menu.get("description"),
            "priceValue": int(menu["priceValue"]),
        }
        for menu in menus
    ]
    return (
        "Classify each supplied existing menu row for whether its listed database price is a "
        "defensible price for one person's lunch budget comparison. Do not infer or create "
        "portion sizes. Use ELIGIBLE only when the row itself clearly represents one person's "
        "meal. Use INELIGIBLE for drinks, alcohol, sides, courses, multi-person portions, "
        "or weight-priced items. Use UNKNOWN whenever portion/budget suitability is unclear. "
        "Flags may contain multiple applicable values from SIDE, DRINK, ALCOHOL, MULTI_PERSON, "
        "COURSE, WEIGHT_BASED. Return only classifications, one for each supplied menuId. "
        "Do not return rationale. Do not alter IDs, names, descriptions, or prices.\nMENUS:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


MenuBudgetResponseSchema = {
    "type": "OBJECT",
    "properties": {
        "classifications": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "menuId": {"type": "INTEGER"},
                    "budgetEligibility": {
                        "type": "STRING",
                        "enum": ["ELIGIBLE", "INELIGIBLE", "UNKNOWN"],
                    },
                    "flags": {
                        "type": "ARRAY",
                        "items": {
                            "type": "STRING",
                            "enum": sorted(ALLOWED_FLAGS),
                        },
                    },
                },
                "required": ["menuId", "budgetEligibility", "flags"],
            },
        }
    },
    "required": ["classifications"],
}


def merge_chunk_result(menus: list[dict], classifications: list[dict]) -> list[dict]:
    """Validate model IDs/enums and fill omitted input rows with UNKNOWN."""
    input_by_id = {int(item["id"]): item for item in menus}
    if len(input_by_id) != len(menus):
        raise ClassificationBatchError("duplicate input menuId")
    seen: set[int] = set()
    result: dict[int, dict] = {}
    try:
        for raw in classifications:
            item = MenuClassification.model_validate(raw)
            menu_id = item.menuId
            if menu_id not in input_by_id:
                raise ClassificationBatchError("unknown output menuId")
            if menu_id in seen:
                raise ClassificationBatchError("duplicate output menuId")
            seen.add(menu_id)
            result[menu_id] = {
                "menuId": menu_id,
                "budgetEligibility": item.budgetEligibility.value,
                "flags": sorted({flag.value for flag in item.flags}),
            }
    except ValidationError as error:
        raise ClassificationBatchError("invalid classification schema") from error
    for menu_id in input_by_id:
        result.setdefault(
            menu_id,
            {"menuId": menu_id, "budgetEligibility": "UNKNOWN", "flags": []},
        )
    return [result[menu_id] for menu_id in input_by_id]


def classify_with_bounded_retry(
    classifier,
    menus: list[dict],
    *,
    sleep=time.sleep,
    before_request=None,
    on_attempt=None,
    on_outcome=None,
) -> dict:
    """One retry for network/5xx only. 429/403 and schema failures stop immediately."""
    attempts = 0
    retries = 0
    while True:
        attempts += 1
        started = time.monotonic()
        if before_request is not None:
            before_request()
        if on_attempt is not None:
            on_attempt(attempts)
        try:
            raw, usage = classifier.classify(menus)
        except Exception as error:  # SDK exceptions differ by transport and response version.
            status_code = getattr(error, "code", None) or getattr(error, "status_code", None)
            diagnostics = _safe_error_diagnostics(error)
            if on_outcome is not None:
                on_outcome(attempts, status_code, diagnostics)
            if status_code == 429 or status_code == 403:
                raise ClassificationBatchError(
                    f"provider stop status {status_code}",
                    attempts=attempts,
                    retries=retries,
                    status_code=status_code,
                    diagnostics=diagnostics,
                ) from error
            transient_server = isinstance(status_code, int) and 500 <= status_code <= 599
            transient_network = error.__class__.__module__.startswith(
                ("httpx", "httpcore")
            ) or isinstance(error, (TimeoutError, ConnectionError, OSError))
            if attempts >= 2 or not (transient_server or transient_network):
                if diagnostics["safeErrorCategory"] == "timeout":
                    reason = "timeout"
                elif isinstance(error, ClassificationBatchError):
                    reason = str(error)
                elif transient_server:
                    reason = "provider 5xx failure"
                else:
                    reason = "network transport failure"
                raise ClassificationBatchError(
                    reason,
                    attempts=attempts,
                    retries=retries,
                    status_code=status_code,
                    diagnostics=diagnostics,
                ) from error
            retries += 1
            sleep(min(8, 2**retries))
            continue
        if on_outcome is not None:
            on_outcome(attempts, None, {"safeErrorCategory": None})
        try:
            merged = merge_chunk_result(menus, raw)
        except ClassificationBatchError as error:
            raise ClassificationBatchError(
                str(error), attempts=attempts, retries=retries
            ) from error
        try:
            return {
                "classifications": merged,
                "omittedMenuIds": sorted(
                    {int(menu["id"]) for menu in menus} - {int(item["menuId"]) for item in raw}
                ),
                "attempts": attempts,
                "retries": retries,
                "latencySeconds": round(time.monotonic() - started, 3),
                "usage": usage,
            }
        except Exception as error:
            raise ClassificationBatchError(
                "structured result handling failed",
                attempts=attempts,
                retries=retries,
            ) from error


def classifier_from_environment(*, client=None) -> GeminiMenuBudgetClassifier:
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY is required")
    # Pass the selected key explicitly: the SDK must not silently select GOOGLE_API_KEY.
    model = os.getenv("GEMINI_MODEL", MODEL_DEFAULT)
    return GeminiMenuBudgetClassifier(api_key=gemini_key, model=model, client=client)
