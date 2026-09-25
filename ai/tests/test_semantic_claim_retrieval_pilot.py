from pathlib import Path

from app.semantic_claim_retrieval_pilot import (
    COLLECTION,
    build_claim_points,
    food_mentions,
    route_query,
)


ROOT = Path(__file__).parents[2] / "AI_Answer"


def test_claim_points_use_approved_claims_and_traceable_normalized_text():
    points = build_claim_points(ROOT)
    assert {point["restaurantId"] for point in points} == {9617, 9731, 9567, 9580}
    assert all(point["embeddingModel"] == "qwen3-embedding:0.6b" for point in points)
    assert all(point["evidenceIds"] and point["pointId"] for point in points)
    assert not any("REVIEW_REQUIRED" in point["embeddingText"] or "REJECTED" in point["embeddingText"] for point in points)
    assert not any("price" in point["embeddingText"].lower() for point in points)
    assert any(point["claimType"] == "FOOD_MENTION" and point["restaurantId"] == 9731 for point in points)
    assert any(point["claimType"] == "FOOD_MENTION" and point["restaurantId"] == 9580 for point in points)
    assert all("공식 메뉴" in point["normalizedClaimText"] for point in points if point["claimType"] == "FOOD_MENTION")


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
