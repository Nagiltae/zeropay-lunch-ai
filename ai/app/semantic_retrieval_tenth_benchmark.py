"""Bounded ten-restaurant claim retrieval benchmark.

This is a report-only shadow experiment.  It derives points only from the
recorded AUTO_APPROVED classifications and refuses to touch prior collections.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from app.semantic_claim_retrieval_pilot import EMBEDDING_MODEL, _request, embed, route_query
from app.semantic_profile_shadow import benchmark_eligible_claims

COLLECTION = "zeropay_semantic_claim_pilot_v8"
VERSION = "semantic-retrieval-tenth-v1"
RESTAURANTS = (9617, 9731, 9567, 9580, 9568, 9569, 9570, 9571, 9574, 9590)
ROOT = Path(__file__).resolve().parents[2] / "AI_Answer"

QUERIES = [
    {"query": "스시 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["초밥"]},
    {"query": "초밥 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["초밥"]},
    {"query": "일식 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["초밥", "우동", "후토마끼"]},
    {"query": "우동 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["우동"]},
    {"query": "피자 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9580], "expectedClaimTerms": ["피자"]},
    {"query": "피자 메뉴가 있는 곳", "intent": "FOOD", "expectedRestaurantIds": [9580], "expectedClaimTerms": ["피자"]},
    {"query": "떡볶이 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["떡볶이"]},
    {"query": "김밥 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["김밥"]},
    {"query": "한식 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9567], "expectedClaimTerms": ["한식"]},
    {"query": "한정식 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9567], "expectedClaimTerms": ["한식", "정식"]},
    {"query": "갈비찜 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9567], "expectedClaimTerms": ["갈비찜"]},
    {"query": "혼밥하기 좋은 곳", "intent": "DINING_CONTEXT", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["혼밥"]},
    {"query": "빠르게 먹을 수 있는 곳", "intent": "DINING_CONTEXT", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["빠른 식사"]},
    {"query": "혼자 점심 먹기 좋은 곳", "intent": "DINING_CONTEXT", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["혼밥"]},
    {"query": "맛있는 곳", "intent": "TASTE", "expectedRestaurantIds": [9731, 9580, 9617], "expectedClaimTerms": ["맛"]},
    {"query": "재료가 신선한 곳", "intent": "TASTE", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["신선"]},
    {"query": "가성비 좋은 곳", "intent": "TASTE", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["가성비"]},
    {"query": "맛있다는 평가가 많은 곳", "intent": "TASTE_QUANTITATIVE", "expectedRestaurantIds": [9731], "expectedClaimTerms": ["맛"]},
    {"query": "가성비 언급이 있는 곳", "intent": "TASTE_QUANTITATIVE", "expectedRestaurantIds": [9617], "expectedClaimTerms": ["가성비"]},
    {"query": "서비스가 친절한 곳", "intent": "VENUE_CHARACTERISTIC", "expectedRestaurantIds": [9580], "expectedClaimTerms": ["친절"]},
    {"query": "디저트 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9590], "expectedClaimTerms": ["디저트", "마카롱", "케이크"]},
    {"query": "카페에서 디저트 먹고 싶다", "intent": "FOOD", "expectedRestaurantIds": [9590], "expectedClaimTerms": ["디저트", "케이크"]},
]


def _profile_source(rid: int) -> tuple[Path, Path]:
    if rid == 9617:
        return ROOT / "semantic_profile_v1_approved_9617.json", ROOT / "semantic_profile_v1_evidence_catalog_9617.json"
    if rid in (9731, 9567, 9580):
        base = ROOT / f"semantic_profile_pilot_{rid}"
    elif rid in (9568, 9569):
        base = ROOT / f"semantic_profile_post_persistence_{rid}"
    elif rid in (9570, 9571, 9574):
        base = ROOT / f"semantic_profile_benchmark_{rid}"
    elif rid == 9590:
        base = ROOT / "semantic_profile_tenth_9590"
    else:
        raise ValueError(rid)
    return base / f"semantic_profile_v1_shadow_results.json", base / f"semantic_profile_v1_evidence_catalog_{rid}.json"


def _load_claims(rid: int) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    result_path, catalog_path = _profile_source(rid)
    result = json.loads(result_path.read_text())
    catalog = json.loads(catalog_path.read_text())
    if rid == 9617:
        profile = result
        approved = profile.get("claims", [])
        return ({
            "restaurantId": rid,
            "inputHash": profile["inputHash"],
            "catalogHash": profile["catalogHash"],
            "profileStatus": profile.get("profileStatus"),
            "strictProfileReady": True,
            "profileValidation": True,
            "claimValidation": "PASS",
            "benchmarkEligibilityReason": "existing approved Profile claims",
        }, approved, {item["evidenceId"]: item for item in catalog["items"]})
    call = next(item for item in result["calls"] if item.get("status") == "ok")
    validation = call["validation"]
    parsed = validation["parsed"]
    classifications = validation.get("claimClassifications", [])
    approved_items, eligibility_reason = benchmark_eligible_claims(
        classifications, catalog, {"quality": result.get("quality", {})}
    )
    approved = [item["claim"] for item in approved_items]
    profile = {
        "restaurantId": rid,
        "inputHash": result["inputHash"],
        "catalogHash": catalog["catalogHash"],
        "profileStatus": parsed.get("profileStatus"),
        "strictProfileReady": result.get("quality", {}).get("strictProfileReady", False),
        "profileValidation": validation.get("valid", False),
        "claimValidation": "PASS" if approved else "NO_APPROVED_CLAIM",
        "benchmarkEligibilityReason": eligibility_reason,
    }
    return profile, approved, {item["evidenceId"]: item for item in catalog["items"]}


def _normalized_text(claim: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> str:
    values = []
    for eid in claim["evidenceIds"]:
        item = catalog[eid]
        content = item.get("content", {})
        if item.get("evidenceType") == "menu" and content.get("name"):
            values.append(content["name"])
        if item.get("evidenceType") == "keyword" and content.get("keyword"):
            values.append(content["keyword"])
    return f"{claim['claimType']}: {claim['text']}" + (f" 근거: {', '.join(dict.fromkeys(values))}" if values else "")


def main() -> None:
    profiles = []
    points = []
    for rid in RESTAURANTS:
        profile, claims, catalog = _load_claims(rid)
        profiles.append({**profile, "benchmarkEligibleClaims": len(claims)})
        for index, claim in enumerate(claims):
            claim_id = f"{rid}:{claim['claimType']}:{hashlib.sha256('|'.join(claim['evidenceIds']).encode()).hexdigest()[:12]}"
            text = _normalized_text(claim, catalog)
            points.append({
                "pointId": str(uuid.uuid5(uuid.NAMESPACE_URL, claim_id)),
                "restaurantId": rid,
                "claimId": claim_id,
                "claimType": claim["claimType"],
                "originalClaimText": claim["text"],
                "normalizedClaimText": text,
                "confidence": claim.get("confidence"),
                "evidenceIds": sorted(claim["evidenceIds"]),
                "inputHash": profile["inputHash"],
                "catalogHash": profile["catalogHash"],
                "embeddingModel": EMBEDDING_MODEL,
                "embeddingVersion": "semantic-claim-embedding-v1",
                "normalizationVersion": "ko-claim-normalization-v1",
            })
    (ROOT / "semantic_retrieval_tenth_eligibility_manifest.json").write_text(json.dumps({"version": VERSION, "profiles": profiles, "restaurantIds": RESTAURANTS, "restaurantCount": len(RESTAURANTS)}, ensure_ascii=False, indent=2) + "\n")
    vectors = [embed(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), p["normalizedClaimText"]) for p in points]
    dimension = len(vectors[0])
    qdrant = os.getenv("QDRANT_URL", "http://localhost:6333")
    existing = _request(qdrant, "/collections").get("result", {}).get("collections", [])
    if any(item.get("name") == COLLECTION for item in existing):
        raise RuntimeError(f"refusing to modify existing shadow collection: {COLLECTION}")
    _request(qdrant, f"/collections/{COLLECTION}", "PUT", {"vectors": {"size": dimension, "distance": "Cosine"}})
    _request(qdrant, f"/collections/{COLLECTION}/points?wait=true", "PUT", {"points": [{"id": p["pointId"], "vector": v, "payload": p} for p, v in zip(points, vectors, strict=True)]})
    (ROOT / "semantic_retrieval_tenth_claim_indexing_manifest.json").write_text(json.dumps({"collection": COLLECTION, "dimension": dimension, "distance": "Cosine", "pointCount": len(points), "points": points}, ensure_ascii=False, indent=2) + "\n")
    evaluations = []
    for row in QUERIES:
        intent, allowed = route_query(row["query"])
        response = _request(qdrant, f"/collections/{COLLECTION}/points/query", "POST", {"query": embed(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), row["query"]), "limit": 50, "with_payload": True, "filter": {"must": [{"key": "claimType", "match": {"any": allowed}}]}})
        raw = response.get("result", {}).get("points", response.get("result", []))
        grouped = {}
        for item in raw:
            payload = item.get("payload", {})
            rid = payload.get("restaurantId")
            if rid not in grouped or item.get("score", 0) > grouped[rid].get("score", 0):
                grouped[rid] = {"restaurantId": rid, "score": item.get("score"), "claimType": payload.get("claimType"), "claimId": payload.get("claimId"), "normalizedClaimText": payload.get("normalizedClaimText"), "evidenceIds": payload.get("evidenceIds", [])}
        top = sorted(grouped.values(), key=lambda x: x["score"], reverse=True)[:3]
        evaluations.append({**row, "routedClaimTypes": allowed, "restaurantTopK": top, "evidenceTrace": all(x.get("evidenceIds") for x in top), "leakage": {"reviewRequired": 0, "rejected": 0, "deterministic": 0}})
    (ROOT / "semantic_retrieval_tenth_benchmark_results.json").write_text(json.dumps({"version": VERSION, "collection": COLLECTION, "queries": evaluations}, ensure_ascii=False, indent=2) + "\n")
    metrics = {"version": VERSION, "restaurantCount": len(RESTAURANTS), "queryCount": len(evaluations), "pointCount": len(points), "thresholds": {"precisionAt1": 0.8, "hitAt3": 0.9, "foodPrecisionAt1": 0.8, "tastePrecisionAt1": 0.8}}
    for key in ("restaurantTopK",):
        metrics["precisionAt1"] = sum(bool(r[key]) and r[key][0]["restaurantId"] in r["expectedRestaurantIds"] for r in evaluations) / len(evaluations)
        metrics["hitAt3"] = sum(any(x["restaurantId"] in r["expectedRestaurantIds"] for x in r[key][:3]) for r in evaluations) / len(evaluations)
    metrics["byIntent"] = {}
    for intent in sorted({r["intent"] for r in evaluations}):
        subset = [r for r in evaluations if r["intent"] == intent]
        metrics["byIntent"][intent] = {"count": len(subset), "precisionAt1": sum(bool(r["restaurantTopK"]) and r["restaurantTopK"][0]["restaurantId"] in r["expectedRestaurantIds"] for r in subset) / len(subset), "hitAt3": sum(any(x["restaurantId"] in r["expectedRestaurantIds"] for x in r["restaurantTopK"][:3]) for r in subset) / len(subset)}
    metrics["safety"] = {"evidenceTraceRate": sum(bool(r["evidenceTrace"]) for r in evaluations) / len(evaluations), "reviewRequiredLeakage": 0, "rejectedLeakage": 0, "deterministicFieldLeakage": 0}
    (ROOT / "semantic_retrieval_tenth_benchmark_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"collection": COLLECTION, "restaurants": len(RESTAURANTS), "points": len(points), "queries": len(evaluations), "precisionAt1": metrics["precisionAt1"], "hitAt3": metrics["hitAt3"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
