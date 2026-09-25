"""Claim-level semantic retrieval shadow pilot.

This module deliberately stays outside the Spring/FastAPI runtime path.  It
uses only approved profile claims and deterministic review-food mentions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from app.semantic_embedding_qdrant_pilot import (
    EMBEDDING_MODEL,
    QUERIES,
    _request,
    embed,
    load_documents,
)

COLLECTION = "zeropay_semantic_claim_pilot_v6"
EMBEDDING_VERSION = "semantic-claim-embedding-v1"
NORMALIZATION_VERSION = "ko-claim-normalization-v1"
RESTAURANT_IDS = (9617, 9731, 9567, 9580)

FOOD_WORDS = re.compile(
    r"(초밥|스시|우동|후토마끼|마끼|피자|파스타|떡볶이|김밥|갈비|오징어|제육|비빔밥|보쌈|고등어|낙지|된장찌개)"
)


def _catalog(root: Path, restaurant_id: int) -> dict[str, dict[str, Any]]:
    path = root / f"semantic_profile_pilot_{restaurant_id}/semantic_profile_v1_evidence_catalog_{restaurant_id}.json"
    if restaurant_id == 9617:
        path = root / "semantic_profile_v1_evidence_catalog_9617.json"
    data = json.loads(path.read_text())
    return {item["evidenceId"]: item for item in data["items"]}


def _approved_profiles(root: Path) -> dict[int, dict[str, Any]]:
    profiles = {9617: json.loads((root / "semantic_profile_v1_approved_9617.json").read_text())}
    for restaurant_id in (9731, 9567, 9580):
        result = json.loads(
            (root / f"semantic_profile_pilot_{restaurant_id}/semantic_profile_v1_shadow_results.json").read_text()
        )
        profiles[restaurant_id] = result["finalProfile"]
    return profiles


def _evidence_terms(claim: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for evidence_id in claim.get("evidenceIds", []):
        item = catalog.get(evidence_id, {})
        content = item.get("content", {})
        if item.get("evidenceType") == "menu" and content.get("name"):
            terms.append(content["name"])
    return terms


def normalize_claim(claim: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> str:
    """Format claims in Korean without adding facts absent from evidence."""
    claim_type = claim["claimType"]
    text = claim.get("text", "")
    if claim_type == "FOOD_TYPE":
        terms = _evidence_terms(claim, catalog)
        if terms:
            if "Korean set meals" in text:
                return f"한식 정식 메뉴에서 {', '.join(dict.fromkeys(terms))}가 확인된다."
            return f"메뉴에서 확인되는 음식 종류: {', '.join(dict.fromkeys(terms))}."
    if claim_type == "MENU_CHARACTERISTIC":
        terms = _evidence_terms(claim, catalog)
        if terms:
            return f"메뉴에서 {', '.join(dict.fromkeys(terms))}가 확인된다."
    keywords = []
    for evidence_id in claim.get("evidenceIds", []):
        item = catalog.get(evidence_id, {})
        content = item.get("content", {})
        if item.get("evidenceType") == "keyword" and isinstance(content, dict):
            keywords.append(str(content.get("keyword", "")))
    if claim_type == "TASTE":
        aspects = []
        joined = " ".join(keywords)
        if "맛" in joined:
            aspects.append("맛있다")
        if "신선" in joined:
            aspects.append("재료가 신선하다")
        if "가성비" in joined:
            aspects.append("가성비가 좋다")
        if aspects:
            return f"고객 평가에서 {', '.join(aspects)}는 언급된다."
    if claim_type == "VENUE_CHARACTERISTIC" and any("친절" in keyword or "서비스" in keyword for keyword in keywords):
        return "고객 평가에서 서비스가 친절하다는 언급이 있다."
    if claim_type == "DINING_CONTEXT" and "혼밥" in text:
        return "고객 평가에서 혼밥과 빠른 식사 이용 맥락이 언급된다."
    return text


def food_mentions(root: Path, restaurant_id: int) -> list[dict[str, Any]]:
    """Create a non-menu FOOD_MENTION only from repeated review keywords."""
    catalog = _catalog(root, restaurant_id)
    mentions = []
    for item in catalog.values():
        content = item.get("content", {})
        if not isinstance(content, dict):
            continue
        keyword = content.get("keyword", "")
        count = content.get("mentionCount", 0)
        if (
            item.get("section") == "review"
            and item.get("status") == "SUCCESS"
            and item.get("evidenceType") == "keyword"
            and count >= 3
            and FOOD_WORDS.search(keyword)
        ):
            word = FOOD_WORDS.search(keyword).group(1)
            mentions.append(
                {
                    "restaurantId": restaurant_id,
                    "claimId": f"{restaurant_id}:FOOD_MENTION:{item['evidenceId']}",
                    "claimType": "FOOD_MENTION",
                    "originalClaimText": f"리뷰 keyword에 {word}이(가) {count}회 언급됨",
                    "normalizedClaimText": f"공식 메뉴가 아니라 고객 리뷰 keyword에서 {word}가 반복 언급된다.",
                    "confidence": "REVIEW_SIGNAL",
                    "evidenceIds": [item["evidenceId"]],
                    "sourceKind": "review_keyword_only",
                    "mentionTerm": word,
                    "mentionCount": count,
                }
            )
    return mentions


def build_claim_points(root: Path) -> list[dict[str, Any]]:
    profiles = _approved_profiles(root)
    points = []
    for restaurant_id in RESTAURANT_IDS:
        catalog = _catalog(root, restaurant_id)
        profile = profiles[restaurant_id]
        for claim in profile.get("claims", []):
            point = {
                "restaurantId": restaurant_id,
                "venueId": profile.get("venueId"),
                "claimId": f"{restaurant_id}:{claim['claimType']}:{hashlib.sha256('|'.join(claim['evidenceIds']).encode()).hexdigest()[:12]}",
                "claimType": claim["claimType"],
                "originalClaimText": claim["text"],
                "normalizedClaimText": normalize_claim(claim, catalog),
                "confidence": claim.get("confidence"),
                "evidenceIds": sorted(claim["evidenceIds"]),
                "mentionCounts": {
                    evidence_id: catalog.get(evidence_id, {}).get("content", {}).get("mentionCount")
                    for evidence_id in claim["evidenceIds"]
                    if isinstance(catalog.get(evidence_id, {}).get("content"), dict)
                    and "mentionCount" in catalog.get(evidence_id, {}).get("content", {})
                },
                "inputHash": profile["inputHash"],
                "catalogHash": profile["catalogHash"],
                "embeddingModel": EMBEDDING_MODEL,
                "embeddingVersion": EMBEDDING_VERSION,
                "normalizationVersion": NORMALIZATION_VERSION,
            }
            point["embeddingText"] = f"{point['claimType']}: {point['normalizedClaimText']}"
            points.append(point)
        for mention in food_mentions(root, restaurant_id):
            mention.update(
                {
                    "inputHash": profile["inputHash"],
                    "catalogHash": profile["catalogHash"],
                    "embeddingModel": EMBEDDING_MODEL,
                    "embeddingVersion": EMBEDDING_VERSION,
                    "normalizationVersion": NORMALIZATION_VERSION,
                    "embeddingText": f"FOOD_MENTION: {mention['normalizedClaimText']}",
                }
            )
            points.append(mention)
    for point in points:
        point["pointId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, point["claimId"]))
    return points


def route_query(query: str) -> tuple[str, list[str]]:
    if re.search(r"혼밥|빠르|단체|회식|식사", query):
        return "DINING_CONTEXT", ["DINING_CONTEXT"]
    if re.search(r"맛|가성비|신선|평가", query):
        return "TASTE", ["TASTE"]
    if re.search(r"넓|분위기|친절|서비스", query):
        return "VENUE_CHARACTERISTIC", ["VENUE_CHARACTERISTIC"]
    if re.search(r"스시|일식|초밥|우동|후토마끼", query):
        return "FOOD", ["FOOD_TYPE", "FOOD_MENTION"]
    if re.search(r"한식|한정식", query):
        return "FOOD", ["FOOD_TYPE"]
    if re.search(r"음식|한식|한정식|피자|파스타|스시|일식|초밥|떡볶이|김밥", query):
        return "FOOD", ["FOOD_TYPE", "MENU_CHARACTERISTIC", "FOOD_MENTION"]
    return "UNKNOWN", ["FOOD_TYPE", "DINING_CONTEXT", "TASTE", "VENUE_CHARACTERISTIC", "MENU_CHARACTERISTIC", "FOOD_MENTION"]


def query_food_terms(query: str) -> list[str]:
    if re.search(r"스시|일식|초밥|우동|후토마끼", query):
        return ["스시", "일식", "초밥", "우동", "후토마끼"]
    if re.search(r"피자|파스타", query):
        return ["피자", "파스타"]
    if re.search(r"떡볶이|김밥", query):
        return ["떡볶이", "김밥"]
    return []


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "AI_Answer"
    ollama = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    qdrant = os.getenv("QDRANT_URL", "http://localhost:6333")
    points = build_claim_points(root)
    vectors = [embed(ollama, point["embeddingText"]) for point in points]
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise RuntimeError("embedding dimension mismatch")
    existing = _request(qdrant, "/collections").get("result", {}).get("collections", [])
    if any(item.get("name") == COLLECTION for item in existing):
        raise RuntimeError(f"pilot collection already exists; refusing to modify: {COLLECTION}")
    _request(qdrant, f"/collections/{COLLECTION}", "PUT", {"vectors": {"size": dimension, "distance": "Cosine"}})
    qdrant_points = [{"id": point["pointId"], "vector": vector, "payload": point} for point, vector in zip(points, vectors, strict=True)]
    _request(qdrant, f"/collections/{COLLECTION}/points?wait=true", "PUT", {"points": qdrant_points})
    baseline = {item["query"]: item for item in json.loads((root / "semantic_embedding_qdrant_query_evaluation.json").read_text())["queries"]}
    evaluations = []
    for query in QUERIES:
        intent, allowed = route_query(query)
        response = _request(
            qdrant,
            f"/collections/{COLLECTION}/points/query",
            "POST",
            {"query": embed(ollama, query), "limit": 50, "with_payload": True, "filter": {"must": [{"key": "claimType", "match": {"any": allowed}}]}},
        )
        raw = response.get("result", {}).get("points", response.get("result", []))
        food_terms = query_food_terms(query)
        if food_terms:
            raw = [
                item for item in raw
                if item.get("payload", {}).get("claimType") != "FOOD_MENTION"
                or item.get("payload", {}).get("mentionTerm") in food_terms
            ]
        ranked: dict[int, dict[str, Any]] = {}
        for item in raw:
            payload = item.get("payload", {})
            rid = payload.get("restaurantId")
            candidate = {"restaurantId": rid, "score": item.get("score"), "claimType": payload.get("claimType"), "claimId": payload.get("claimId"), "normalizedClaimText": payload.get("normalizedClaimText"), "originalClaimText": payload.get("originalClaimText"), "evidenceIds": payload.get("evidenceIds", [])}
            if rid not in ranked or candidate["score"] > ranked[rid]["score"]:
                ranked[rid] = candidate
        aggregated = sorted(ranked.values(), key=lambda value: value["score"], reverse=True)[:3]
        evaluations.append({"query": query, "intent": intent, "allowedClaimTypes": allowed, "claimTopK": raw[:10], "restaurantTopK": aggregated, "baselineTopK": baseline[query]["topK"], "assessment": "PENDING_MANUAL_REVIEW"})
    manifest = {"collection": COLLECTION, "embeddingModel": EMBEDDING_MODEL, "embeddingVersion": EMBEDDING_VERSION, "normalizationVersion": NORMALIZATION_VERSION, "dimension": dimension, "distance": "Cosine", "restaurantIds": list(RESTAURANT_IDS), "pointCount": len(points), "points": points}
    (root / "semantic_claim_retrieval_indexing_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (root / "semantic_claim_retrieval_query_routing_evaluation.json").write_text(json.dumps({"collection": COLLECTION, "queries": evaluations}, ensure_ascii=False, indent=2) + "\n")
    (root / "semantic_claim_retrieval_comparison.json").write_text(json.dumps({"baselineCollection": "zeropay_semantic_profile_pilot_v1", "claimCollection": COLLECTION, "queries": evaluations}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"collection": COLLECTION, "dimension": dimension, "points": len(points), "queries": len(evaluations)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
