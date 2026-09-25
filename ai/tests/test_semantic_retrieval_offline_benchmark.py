from app.semantic_retrieval_offline_benchmark import DATASET


def test_benchmark_ground_truth_is_fixed_and_evidence_backed():
    assert len(DATASET) == 20
    assert {row["intent"] for row in DATASET} >= {"FOOD", "DINING_CONTEXT", "TASTE", "TASTE_QUANTITATIVE", "VENUE_CHARACTERISTIC"}
    assert all(row["expectedRestaurantIds"] for row in DATASET)
    assert all(row["expectedClaimTerms"] for row in DATASET)
    assert all(row["evidenceIds"] for row in DATASET)


def test_benchmark_does_not_expand_beyond_safe_pilot_restaurants():
    allowed = {9617, 9731, 9567, 9580}
    assert all(set(row["expectedRestaurantIds"]).issubset(allowed) for row in DATASET)
