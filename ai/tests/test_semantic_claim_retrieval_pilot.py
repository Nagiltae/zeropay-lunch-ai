from pathlib import Path

import pytest

from app.semantic_claim_retrieval_pilot import (
    COLLECTION,
    build_claim_points,
    food_mentions,
    route_query,
)
from app.semantic_retrieval_tenth_benchmark import _normalized_text

ROOT = Path(__file__).parents[2] / "AI_Answer"


def test_legacy_claim_points_fail_closed_without_source_scope_contract():
    with pytest.raises(ValueError, match="CLAIM_NOT_INDEXABLE"):
        build_claim_points(ROOT)


def test_tenth_benchmark_text_builder_rejects_legacy_claims():
    with pytest.raises(ValueError, match="CLAIM_NOT_INDEXABLE"):
        _normalized_text({"claimType": "DINING_CONTEXT", "text": "혼밥하기 좋다"}, {})


def test_food_mentions_require_successful_repeated_review_keywords():
    mentions = food_mentions(ROOT, 9731)
    text = " ".join(item["normalizedClaimText"] for item in mentions)
    assert "초밥" in text
    assert "우동" in text
    assert "후토마끼" in text
    assert all(item["sourceKind"] == "review_keyword_only" for item in mentions)


def test_query_router_limits_claim_types():
    assert route_query("스시나 일식이 먹고 싶다")[1] == ["FOOD_TYPE", "FOOD_MENTION"]
    assert route_query("한식이 먹고 싶다")[1] == ["FOOD_TYPE"]
    assert route_query("혼밥하기 좋은 음식점")[1] == ["DINING_CONTEXT"]
    assert route_query("가성비 좋은 음식점")[1] == ["TASTE"]
    assert COLLECTION == "zeropay_semantic_claim_pilot_v6"
