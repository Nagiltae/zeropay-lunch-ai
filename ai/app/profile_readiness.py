"""Shared, fail-closed readiness policy for Semantic Profile inputs."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any


def freshness_ttl_seconds() -> int | None:
    raw = os.environ.get("NAVER_DETAIL_STALE_AFTER_SECONDS", "2592000").strip().lower()
    if raw in {"", "off", "none", "disabled"}:
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError("NAVER_DETAIL_STALE_AFTER_SECONDS must be numeric or off") from error
    return int(value) if value > 0 else None


def _timestamp(value: Any) -> datetime | None:
    if not value or str(value) in {"NULL", "None"}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def is_source_grounded_hour(row: dict[str, Any]) -> bool:
    day = str(row.get("day") or row.get("day_of_week") or "").strip()
    opening = str(row.get("open_time") or "").strip()
    closing = str(row.get("close_time") or "").strip()
    description = str(row.get("description") or "")
    if not day or not opening or not closing or not description:
        return False
    pattern = (
        rf"(?<![가-힣]){re.escape(day)}(?:\([^)]*\))?\s+"
        rf"{re.escape(opening)}\s*[-~]\s*(?:다음\s*날\s*)?{re.escape(closing)}(?!\d)"
    )
    return re.search(pattern, description) is not None


def assess_profile_readiness(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    """Return one consistent READY/NOT_READY decision and stable reason codes.

    Expected record keys: lifecycle, menus, businessHours, numericPlaceId,
    ownerCount, verificationStatus, verificationPlaceId, active and eligibility.
    """
    now = now or datetime.now(UTC)
    now = now.replace(tzinfo=UTC) if now.tzinfo is None else now
    ttl_seconds = freshness_ttl_seconds() if ttl_seconds is None else ttl_seconds
    lifecycle = {str(row.get("section")): row for row in record.get("lifecycle", [])}
    reasons: list[str] = []

    if record.get("active") is False or str(record.get("active")) in {"0", "False", "false"}:
        reasons.append("INACTIVE")
    if record.get("eligibility") not in {"ELIGIBLE", True}:
        reasons.append("NOT_ELIGIBLE")

    required = {
        "menu": "NO_MENU_SUCCESS",
        "business_hours": "NO_BUSINESS_HOURS_SUCCESS",
        "review": "NO_REVIEW_SUCCESS",
    }
    for section, reason in required.items():
        state = lifecycle.get(section)
        if not state or state.get("state") != "SUCCESS":
            reasons.append(reason)
        elif ttl_seconds is not None:
            checked = _timestamp(state.get("checkedAt"))
            if checked is None or (now - checked.astimezone(UTC)).total_seconds() > ttl_seconds:
                reasons.append("STALE")

    menus = record.get("menus", [])
    if not any(
        (menu.get("price_value") is not None and str(menu.get("price_value")).strip() != "")
        or bool(str(menu.get("price_text") or "").strip())
        for menu in menus
    ):
        reasons.append("NO_PRICED_MENU")

    hours = record.get("businessHours", [])
    if not any(is_source_grounded_hour(row) for row in hours):
        reasons.append("NO_STRUCTURED_HOURS")

    place_id = str(record.get("numericPlaceId") or "")
    if not re.fullmatch(r"\d+", place_id):
        reasons.append("NO_NUMERIC_PLACE_ID")
    if int(record.get("ownerCount") or 0) != 1:
        reasons.append("PLACE_ID_CONFLICT")
    verified_place_id = str(record.get("verificationPlaceId") or "")
    if record.get("verificationStatus") != "VERIFIED" or verified_place_id not in {"", place_id}:
        reasons.append("NOT_VERIFIED")

    reasons = list(dict.fromkeys(reasons))
    return {
        "status": "READY" if not reasons else "NOT_READY",
        "ready": not reasons,
        "reasons": reasons,
        "freshnessTtlSeconds": ttl_seconds,
    }
