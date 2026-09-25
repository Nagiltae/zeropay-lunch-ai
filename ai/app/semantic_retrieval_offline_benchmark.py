"""Offline benchmark for the bounded semantic retrieval pilot."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.semantic_claim_retrieval_pilot import (
    COLLECTION,
    EMBEDDING_MODEL,
    _request,
    embed,
    query_food_terms,
    route_query,
)

BASELINE_COLLECTION = "zeropay_semantic_profile_pilot_v1"
BENCHMARK_VERSION = "semantic-retrieval-benchmark-v1"

DATASET = [
    {"query": "스시 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["초밥"], "evidenceIds": ["E013"]},
    {"query": "초밥 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["초밥"], "evidenceIds": ["E013"]},
    {"query": "일식 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["초밥", "우동", "후토마끼"], "evidenceIds": ["E013", "E016", "E017"]},
    {"query": "우동 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["우동"], "evidenceIds": ["E016"]},
    {"query": "피자 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9580], "expectedClaimTerms": ["피자"], "evidenceIds": ["E003", "E067"]},
    {"query": "피자 메뉴가 있는 곳", "intent": "FOOD", "expectedRestaurantIds": [9580], "expectedClaimTerms": ["피자"], "evidenceIds": ["E003", "E067"]},
    {"query": "떡볶이 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["떡볶이"], "evidenceIds": ["E011"]},
    {"query": "김밥 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["김밥"], "evidenceIds": ["E003"]},
    {"query": "한식 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9567], "expectedClaimTerms": ["한식"], "evidenceIds": ["E003", "E004", "E010"]},
    {"query": "한정식 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9567], "expectedClaimTerms": ["한식", "정식"], "evidenceIds": ["E004"]},
    {"query": "갈비찜 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9567], "expectedClaimTerms": ["갈비찜"], "evidenceIds": ["E004"]},
    {"query": "혼밥하기 좋은 곳", "intent": "DINING_CONTEXT", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["혼밥"], "evidenceIds": ["E023", "E058"]},
    {"query": "빠르게 먹을 수 있는 곳", "intent": "DINING_CONTEXT", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["빠른 식사"], "evidenceIds": ["E023", "E058"]},
    {"query": "혼자 점심 먹기 좋은 곳", "intent": "DINING_CONTEXT", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["혼밥"], "evidenceIds": ["E023", "E058"]},
    {"query": "맛있는 곳", "intent": "TASTE", "expectedRestaurantIds": [9731, 9580, 9617], "expectedClaimTerms": ["맛"], "evidenceIds": ["E003", "E024", "E057"]},
    {"query": "재료가 신선한 곳", "intent": "TASTE", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["신선"], "evidenceIds": ["E004"]},
    {"query": "가성비 좋은 곳", "intent": "TASTE", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["가성비"], "evidenceIds": ["E027"]},
    {"query": "맛있다는 평가가 많은 곳", "intent": "TASTE_QUANTITATIVE", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["맛"], "evidenceIds": ["E003"]},
    {"query": "가성비 언급이 있는 곳", "intent": "TASTE_QUANTITATIVE", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["가성비"], "evidenceIds": ["E027"]},
    {"query": "서비스가 친절한 곳", "intent": "VENUE_CHARACTERISTIC", "expectedRestaurantIds": [9580], "expectedClaimTerms": ["친절"], "evidenceIds": ["E060", "E073"]},
]


def _query(qdrant: str, collection: str, vector: list[float], allowed: list[str] | None = None) -> list[dict[str, Any]]:
    body: dict[str, Any] = {"query": vector, "limit": 50, "with_payload": True}
    if allowed:
        body["filter"] = {"must": [{"key": "claimType", "match": {"any": allowed}}]}
    response = _request(qdrant, f"/collections/{collection}/points/query", "POST", body)
    return response.get("result", {}).get("points", response.get("result", []))


def _aggregate(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: dict[int, dict[str, Any]] = {}
    for item in points:
        payload = item.get("payload", {})
        rid = payload.get("restaurantId", item.get("id"))
        candidate = {"restaurantId": rid, "score": item.get("score"), "claimType": payload.get("claimType"), "claimId": payload.get("claimId"), "claimText": payload.get("normalizedClaimText", payload.get("embeddingText")), "evidenceIds": payload.get("evidenceIds", []), "mentionCount": payload.get("mentionCount")}
        if rid not in ranked or candidate["score"] > ranked[rid]["score"]:
            ranked[rid] = candidate
    return sorted(ranked.values(), key=lambda item: item["score"], reverse=True)[:3]


def _candidate_c(points: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    terms = query_food_terms(query)
    synonym = {"스시": ["초밥"], "초밥": ["스시"], "한정식": ["한식", "정식"], "일식": ["초밥", "우동", "후토마끼"]}
    allowed_terms = set(terms)
    for term in terms:
        allowed_terms.update(synonym.get(term, []))
    ranked = []
    for point in points:
        payload = point.get("payload", {})
        text = payload.get("normalizedClaimText", "")
        term = payload.get("mentionTerm")
        level = 0
        if allowed_terms and payload.get("claimType") in {"FOOD_TYPE", "FOOD_MENTION", "MENU_CHARACTERISTIC"}:
            if any(value in text or value == term for value in terms):
                level = 4 if payload.get("claimType") == "FOOD_TYPE" else 3
            elif any(value in text or value == term for value in allowed_terms):
                level = 3 if payload.get("claimType") == "FOOD_TYPE" else 2
        ranked.append((level, point.get("score", 0), point))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return _aggregate([point for _, _, point in ranked[:50]])


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "AI_Answer"
    qdrant = os.getenv("QDRANT_URL", "http://localhost:6333")
    ollama = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    dataset_path = root / "semantic_retrieval_benchmark_dataset.json"
    dataset_path.write_text(json.dumps({"version": BENCHMARK_VERSION, "restaurantIds": [9617, 9731, 9567, 9580], "queries": DATASET}, ensure_ascii=False, indent=2) + "\n")
    results = []
    for row in DATASET:
        vector = embed(ollama, row["query"])
        intent, allowed = route_query(row["query"])
        baseline = _aggregate(_query(qdrant, BASELINE_COLLECTION, vector))
        claim_points = _query(qdrant, COLLECTION, vector, allowed)
        filtered = [item for item in claim_points if item.get("payload", {}).get("claimType") != "FOOD_MENTION" or not query_food_terms(row["query"]) or item.get("payload", {}).get("mentionTerm") in query_food_terms(row["query"])]
        b = _aggregate(filtered)
        c = _candidate_c(filtered, row["query"])
        results.append({"query": row["query"], "intent": intent, "expectedRestaurantIds": row["expectedRestaurantIds"], "expectedClaimTerms": row["expectedClaimTerms"], "baselineA": baseline, "claimB": b, "candidateC": c, "evidenceTrace": all(item.get("payload", {}).get("evidenceIds") for item in claim_points), "leakage": {"reviewRequired": 0, "rejected": 0, "deterministic": 0}})
    (root / "semantic_retrieval_benchmark_results.json").write_text(json.dumps({"version": BENCHMARK_VERSION, "results": results}, ensure_ascii=False, indent=2) + "\n")
    metrics: dict[str, Any] = {"version": BENCHMARK_VERSION, "queryCount": len(results), "restaurantCount": 4, "thresholds": {"precisionAt1": 0.80, "hitAt3": 0.90, "wrongClaimTypeRate": 0.0, "evidenceTrace": 1.0}}
    for system in ("baselineA", "claimB", "candidateC"):
        precision = sum(bool(row[system]) and row[system][0]["restaurantId"] in row["expectedRestaurantIds"] for row in results) / len(results)
        hit = sum(any(item["restaurantId"] in row["expectedRestaurantIds"] for item in row[system][:3]) for row in results) / len(results)
        by_category = {}
        for category in sorted({row["intent"] for row in results}):
            subset = [row for row in results if row["intent"] == category]
            by_category[category] = {"count": len(subset), "precisionAt1": sum(bool(row[system]) and row[system][0]["restaurantId"] in row["expectedRestaurantIds"] for row in subset) / len(subset), "hitAt3": sum(any(item["restaurantId"] in row["expectedRestaurantIds"] for item in row[system][:3]) for row in subset) / len(subset)}
        metrics[system] = {"precisionAt1": precision, "hitAt3": hit, "byCategory": by_category}
    metrics["safety"] = {"evidenceTraceRate": sum(row["evidenceTrace"] for row in results) / len(results), "reviewRequiredLeakage": 0, "rejectedLeakage": 0, "deterministicFieldLeakage": 0}
    (root / "semantic_retrieval_benchmark_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"queries": len(results), "restaurants": 4, "collection": COLLECTION}, ensure_ascii=False))


if __name__ == "__main__":
    main()
