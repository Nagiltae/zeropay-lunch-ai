"""Deterministic source provenance and indexability guard for semantic claims."""

from __future__ import annotations

from typing import Any

LISTING_SOURCES = frozenset({"menu"})
CUSTOMER_SOURCES = frozenset({"review", "keyword"})
CUSTOMER_SEARCH_PREFIX = "고객 리뷰 기반 정보: "


def derive_source_scope(evidence_sources: list[str]) -> str:
    """Derive scope from resolved source types; never consult claim wording."""
    if not evidence_sources:
        return "UNKNOWN"
    normalized = {
        source.casefold() if isinstance(source, str) else "" for source in evidence_sources
    }
    if not normalized.issubset(LISTING_SOURCES | CUSTOMER_SOURCES):
        return "UNKNOWN"
    has_listing = bool(normalized & LISTING_SOURCES)
    has_customer = bool(normalized & CUSTOMER_SOURCES)
    if has_listing and has_customer:
        return "MIXED"
    if has_listing:
        return "LISTING_FACT"
    if has_customer:
        return "CUSTOMER_REPORTED"
    return "UNKNOWN"


def evaluate_scoped_claim(
    *,
    raw_claim_text: str,
    evidence_sources: list[str],
    deterministic_valid: bool,
    exact_quote_valid: bool,
    semantic_approved: bool,
    atomic_assertion_count: int | None,
) -> dict[str, Any]:
    """Build safe search text and a fail-closed indexing decision.

    `semantic_approved` preserves the verifier result. `indexable` additionally
    requires integrity, atomicity, a known unmixed source scope, and a scoped
    representation. The raw Generator text is never promoted to search text for
    customer-derived claims.
    """
    source_scope = derive_source_scope(evidence_sources)
    safe_text: str | None = None
    reasons: list[str] = []
    if source_scope == "LISTING_FACT":
        safe_text = raw_claim_text.strip() or None
    elif source_scope == "CUSTOMER_REPORTED":
        if raw_claim_text.strip():
            safe_text = f"{CUSTOMER_SEARCH_PREFIX}{raw_claim_text.strip()}"
    elif source_scope == "MIXED":
        reasons.append("MIXED_SOURCE_SCOPE")
    else:
        reasons.append("UNKNOWN_SOURCE_SCOPE")

    if not deterministic_valid:
        reasons.append("DETERMINISTIC_VALIDATION_FAILED")
    if not exact_quote_valid:
        reasons.append("EXACT_QUOTE_INVALID")
    if not semantic_approved:
        reasons.append("SEMANTIC_NOT_APPROVED")
    if atomic_assertion_count != 1:
        reasons.append("NON_ATOMIC")
    if not safe_text:
        reasons.append("SCOPED_SEARCH_TEXT_MISSING")

    indexable = not reasons
    return {
        "sourceScope": source_scope,
        "rawClaimText": raw_claim_text,
        "searchText": safe_text,
        "semanticApproved": semantic_approved,
        "indexable": indexable,
        "indexText": safe_text if indexable else None,
        "rejectReasons": reasons,
    }


def embedding_text_from_indexable_claims(claims: list[dict[str, Any]]) -> str:
    """Use only guard-approved searchText; reject legacy/raw claim fallbacks."""
    if not claims:
        raise ValueError("NO_INDEXABLE_CLAIMS")
    texts: list[str] = []
    for claim in claims:
        if claim.get("indexable") is not True:
            raise ValueError("CLAIM_NOT_INDEXABLE")
        source_scope = claim.get("sourceScope")
        if source_scope not in {"LISTING_FACT", "CUSTOMER_REPORTED"}:
            raise ValueError("INVALID_SOURCE_SCOPE")
        raw_claim = claim.get("rawClaimText", claim.get("claimText"))
        if not isinstance(raw_claim, str) or not raw_claim.strip():
            raise ValueError("RAW_CLAIM_TEXT_MISSING")
        search_text = claim.get("searchText")
        if not isinstance(search_text, str) or not search_text.strip():
            raise ValueError("SCOPED_SEARCH_TEXT_MISSING")
        if source_scope == "CUSTOMER_REPORTED":
            if raw_claim == search_text:
                raise ValueError("RAW_CUSTOMER_CLAIM_USED_AS_SEARCH_TEXT")
            if search_text != f"{CUSTOMER_SEARCH_PREFIX}{raw_claim.strip()}":
                raise ValueError("CUSTOMER_SCOPE_TEXT_MISMATCH")
        elif search_text != raw_claim.strip():
            raise ValueError("LISTING_SEARCH_TEXT_MISMATCH")
        texts.append(search_text.strip())
    return " ".join(texts)
