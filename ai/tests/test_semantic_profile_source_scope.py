import pytest

from app.semantic_profile_source_scope import (
    CUSTOMER_SEARCH_PREFIX,
    derive_source_scope,
    embedding_text_from_indexable_claims,
    evaluate_scoped_claim,
)


def _evaluate(sources, *, atom_count=1, valid=True, quote=True, approved=True):
    return evaluate_scoped_claim(
        raw_claim_text="혼밥하기에 좋은 식당입니다.",
        evidence_sources=sources,
        deterministic_valid=valid,
        exact_quote_valid=quote,
        semantic_approved=approved,
        atomic_assertion_count=atom_count,
    )


def test_source_scope_is_deterministic_from_resolved_evidence_types():
    assert derive_source_scope(["menu"]) == "LISTING_FACT"
    assert derive_source_scope(["review"]) == "CUSTOMER_REPORTED"
    assert derive_source_scope(["keyword"]) == "CUSTOMER_REPORTED"
    assert derive_source_scope(["menu", "review"]) == "MIXED"
    assert derive_source_scope(["menu", "unexpected"]) == "UNKNOWN"
    assert derive_source_scope([]) == "UNKNOWN"


def test_customer_claim_keeps_raw_text_and_indexes_only_scoped_representation():
    result = _evaluate(["keyword"])
    assert result["semanticApproved"] is True
    assert result["sourceScope"] == "CUSTOMER_REPORTED"
    assert result["searchText"] == f"{CUSTOMER_SEARCH_PREFIX}혼밥하기에 좋은 식당입니다."
    assert result["indexable"] is True
    assert result["indexText"] == result["searchText"]
    assert result["indexText"] != "혼밥하기에 좋은 식당입니다."


def test_listing_claim_uses_claim_without_customer_prefix():
    result = evaluate_scoped_claim(
        raw_claim_text="메뉴에 순대국이 있다.",
        evidence_sources=["menu"],
        deterministic_valid=True,
        exact_quote_valid=True,
        semantic_approved=True,
        atomic_assertion_count=1,
    )
    assert result["sourceScope"] == "LISTING_FACT"
    assert result["searchText"] == "메뉴에 순대국이 있다."
    assert result["indexable"] is True


@pytest.mark.parametrize(
    ("sources", "scope", "reason"),
    [
        (["menu", "review"], "MIXED", "MIXED_SOURCE_SCOPE"),
        (["new_source"], "UNKNOWN", "UNKNOWN_SOURCE_SCOPE"),
    ],
)
def test_mixed_and_unknown_sources_fail_closed(sources, scope, reason):
    result = _evaluate(sources)
    assert result["sourceScope"] == scope
    assert result["indexable"] is False
    assert result["indexText"] is None
    assert reason in result["rejectReasons"]


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"valid": False}, "DETERMINISTIC_VALIDATION_FAILED"),
        ({"quote": False}, "EXACT_QUOTE_INVALID"),
        ({"approved": False}, "SEMANTIC_NOT_APPROVED"),
        ({"atom_count": 2}, "NON_ATOMIC"),
    ],
)
def test_existing_quality_failures_remain_non_indexable(kwargs, reason):
    result = _evaluate(["review"], **kwargs)
    assert result["indexable"] is False
    assert reason in result["rejectReasons"]


def test_customer_raw_claim_or_missing_scoped_text_cannot_be_embedded():
    with pytest.raises(ValueError, match="RAW_CUSTOMER_CLAIM_USED_AS_SEARCH_TEXT"):
        embedding_text_from_indexable_claims(
            [
                {
                    "indexable": True,
                    "sourceScope": "CUSTOMER_REPORTED",
                    "claimText": "고객이 친절하다고 평가했다.",
                    "searchText": "고객이 친절하다고 평가했다.",
                }
            ]
        )
    with pytest.raises(ValueError, match="SCOPED_SEARCH_TEXT_MISSING"):
        embedding_text_from_indexable_claims(
            [{"indexable": True, "sourceScope": "CUSTOMER_REPORTED", "claimText": "x"}]
        )
    with pytest.raises(ValueError, match="INVALID_SOURCE_SCOPE"):
        embedding_text_from_indexable_claims(
            [
                {
                    "indexable": True,
                    "sourceScope": "MIXED",
                    "claimText": "raw",
                    "searchText": "scoped",
                }
            ]
        )
    with pytest.raises(ValueError, match="RAW_CLAIM_TEXT_MISSING"):
        embedding_text_from_indexable_claims(
            [
                {
                    "indexable": True,
                    "sourceScope": "LISTING_FACT",
                    "searchText": "메뉴에 순대국이 있다.",
                }
            ]
        )


def test_embedding_text_uses_only_scoped_search_text():
    claims = [
        {
            "indexable": True,
            "sourceScope": "CUSTOMER_REPORTED",
            "claimText": "혼밥하기 좋은 식당이다.",
            "searchText": f"{CUSTOMER_SEARCH_PREFIX}혼밥하기 좋은 식당이다.",
        },
        {
            "indexable": True,
            "sourceScope": "LISTING_FACT",
            "claimText": "메뉴에 순대국이 있다.",
            "searchText": "메뉴에 순대국이 있다.",
        },
    ]
    assert embedding_text_from_indexable_claims(claims) == (
        f"{CUSTOMER_SEARCH_PREFIX}혼밥하기 좋은 식당이다. 메뉴에 순대국이 있다."
    )


def test_indexer_rejects_changed_scoped_text_for_both_source_scopes():
    customer = {
        "indexable": True,
        "sourceScope": "CUSTOMER_REPORTED",
        "rawClaimText": "혼밥하기 좋은 식당이다.",
        "searchText": f"{CUSTOMER_SEARCH_PREFIX}다른 사실이다.",
    }
    listing = {
        "indexable": True,
        "sourceScope": "LISTING_FACT",
        "rawClaimText": "메뉴에 순대국이 있다.",
        "searchText": "메뉴에 다른 메뉴가 있다.",
    }
    with pytest.raises(ValueError, match="CUSTOMER_SCOPE_TEXT_MISMATCH"):
        embedding_text_from_indexable_claims([customer])
    with pytest.raises(ValueError, match="LISTING_SEARCH_TEXT_MISMATCH"):
        embedding_text_from_indexable_claims([listing])
