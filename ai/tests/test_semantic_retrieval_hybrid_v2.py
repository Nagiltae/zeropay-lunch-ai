from app.semantic_retrieval_hybrid_v2 import GROUND_TRUTH, _food_terms, _route_v2


def test_food_router_does_not_fallback_to_all_claim_types():
    intent, claim_types = _route_v2("카페에서 디저트 먹고 싶다")
    assert intent == "FOOD"
    assert claim_types == ["FOOD_TYPE", "FOOD_MENTION", "MENU_CHARACTERISTIC"]


def test_sushi_synonym_and_japanese_category_are_distinct():
    assert _food_terms("스시 먹고 싶다") == (["스시"], ["초밥"], ["스시", "초밥"])
    assert _food_terms("일식 먹고 싶다")[2] == ["초밥", "우동", "후토마끼"]


def test_ground_truth_v2_is_multilabel_and_has_evidence_reasons():
    pizza = next(row for row in GROUND_TRUTH if row["query"] == "피자 먹고 싶다")
    assert pizza["expectedRestaurantIds"] == [9580, 9571]
    assert pizza["groundTruthReason"]
