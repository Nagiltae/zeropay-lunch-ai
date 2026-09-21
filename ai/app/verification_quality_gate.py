"""Provider/LLM verification state mapping and downstream safety gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VerificationDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class VerificationResult:
    decision: VerificationDecision
    reason: str
    model: str | None = None


def source_fingerprint(source: dict[str, Any]) -> str:
    """Stable fingerprint of source fields used by Entity Resolution."""
    fields = {
        key: source.get(key)
        for key in (
            "external_merchant_id", "name", "address", "detail_address",
            "latitude", "longitude", "legal_dong_code", "industry_code",
            "business_status_name", "provider_institution_code",
        )
    }
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def map_semantic_result(
    *, final_decision: str | None, business_type: str | None,
    location_scope: str | None, reason: str = "", model: str | None = None,
) -> VerificationResult:
    """Map Qwen's structured result without adding semantic rules in code."""
    if final_decision == "ACCEPT":
        return VerificationResult(VerificationDecision.ACCEPT, reason or "MATCHED", model)
    if final_decision == "REJECT":
        reject_reason = reason or (
            "NON_FOOD" if business_type == "NON_FOOD" else
            "OUT_OF_SCOPE" if location_scope == "OUT_OF_SCOPE" else "NO_MATCH"
        )
        return VerificationResult(VerificationDecision.REJECT, reject_reason, model)
    return VerificationResult(VerificationDecision.UNKNOWN, reason or "SEMANTIC_UNCERTAIN", model)


def technical_unknown(reason: str, model: str | None = None) -> VerificationResult:
    return VerificationResult(VerificationDecision.UNKNOWN, reason, model)


def downstream_allowed(result: VerificationResult) -> bool:
    return result.decision is VerificationDecision.ACCEPT


def recommendation_eligibility(result: VerificationResult) -> str:
    return {VerificationDecision.ACCEPT: "ELIGIBLE",
            VerificationDecision.REJECT: "INELIGIBLE",
            VerificationDecision.UNKNOWN: "UNKNOWN"}[result.decision]


def can_reuse_rejection(
    cached: VerificationResult | None, cached_fingerprint: str | None,
    current_fingerprint: str,
) -> bool:
    return (
        cached is not None
        and cached.decision is VerificationDecision.REJECT
        and cached_fingerprint == current_fingerprint
    )
