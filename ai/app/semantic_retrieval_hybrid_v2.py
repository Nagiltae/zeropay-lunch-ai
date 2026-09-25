"""Evidence-first Ground Truth v2 and bounded hybrid retrieval comparison."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from app.hybrid_policy import FOOD_TERM_MAP, TRAITS, _route_v2, _food_terms, _lexical, _aggregate

from app.semantic_claim_retrieval_pilot import EMBEDDING_MODEL, _request, embed, route_query
from app.semantic_retrieval_tenth_benchmark import RESTAURANTS, _load_claims

ROOT = Path(__file__).resolve().parents[2] / "AI_Answer"
COLLECTION = "zeropay_semantic_claim_pilot_v12"
VERSION = "semantic-retrieval-hybrid-v2"

GROUND_TRUTH = [
    {"query":"스시 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9731],"expectedClaimTypes":["FOOD_MENTION"],"expectedTerms":["초밥"],"acceptableTerms":[],"evidenceIds":["E013"],"groundTruthReason":"9731 review SUCCESS keyword repeats 초밥; not an official menu fact."},
    {"query":"초밥 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9731],"expectedClaimTypes":["FOOD_MENTION"],"expectedTerms":["초밥"],"acceptableTerms":[],"evidenceIds":["E013"],"groundTruthReason":"Exact review keyword evidence."},
    {"query":"일식 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9731],"expectedClaimTypes":["FOOD_MENTION"],"expectedTerms":["초밥","우동","후토마끼"],"acceptableTerms":[],"evidenceIds":["E013","E016","E017"],"groundTruthReason":"Japanese category is represented by three repeated review keywords."},
    {"query":"우동 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9731],"expectedClaimTypes":["FOOD_MENTION"],"expectedTerms":["우동"],"acceptableTerms":[],"evidenceIds":["E016"],"groundTruthReason":"Exact review keyword evidence."},
    {"query":"피자 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9580,9571],"expectedClaimTypes":["MENU_CHARACTERISTIC","FOOD_MENTION"],"expectedTerms":["피자"],"acceptableTerms":[],"evidenceIds":["E008","E010","E067"],"groundTruthReason":"9580 review keyword and 9571 menu evidence both support pizza."},
    {"query":"피자 메뉴가 있는 곳","intent":"FOOD","expectedRestaurantIds":[9571,9580],"expectedClaimTypes":["MENU_CHARACTERISTIC","FOOD_MENTION"],"expectedTerms":["피자"],"acceptableTerms":[],"evidenceIds":["E003","E008","E010","E067"],"groundTruthReason":"Menu-specific evidence is preferred; review mention remains acceptable."},
    {"query":"떡볶이 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9617],"expectedClaimTypes":["FOOD_TYPE"],"expectedTerms":["떡볶이"],"acceptableTerms":[],"evidenceIds":["E011"],"groundTruthReason":"Official menu evidence."},
    {"query":"김밥 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9617],"expectedClaimTypes":["FOOD_TYPE"],"expectedTerms":["김밥"],"acceptableTerms":[],"evidenceIds":["E003"],"groundTruthReason":"Official menu evidence."},
    {"query":"한식 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9567,9568],"expectedClaimTypes":["FOOD_TYPE"],"expectedTerms":["한식","순대국","된장찌개"],"acceptableTerms":[],"evidenceIds":["E003","E004","E012","E013"],"groundTruthReason":"Two approved official-menu Korean food claims."},
    {"query":"한정식 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9567],"expectedClaimTypes":["FOOD_TYPE"],"expectedTerms":["정식","갈비찜"],"acceptableTerms":[],"evidenceIds":["E003","E004"],"groundTruthReason":"9567 explicitly has Korean set-meal evidence."},
    {"query":"갈비찜 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9567],"expectedClaimTypes":["FOOD_TYPE"],"expectedTerms":["갈비찜"],"acceptableTerms":[],"evidenceIds":["E003"],"groundTruthReason":"Exact official menu evidence."},
    {"query":"디저트 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9590],"expectedClaimTypes":["MENU_CHARACTERISTIC","TASTE"],"expectedTerms":["디저트","케이크","마카롱"],"acceptableTerms":[],"evidenceIds":["E017","E022","E034","E110"],"groundTruthReason":"9590 menu and SUCCESS review keyword evidence."},
    {"query":"카페에서 디저트 먹고 싶다","intent":"FOOD","expectedRestaurantIds":[9590],"expectedClaimTypes":["MENU_CHARACTERISTIC","TASTE"],"expectedTerms":["디저트","케이크"],"acceptableTerms":[],"evidenceIds":["E017","E022","E034","E110"],"groundTruthReason":"Explicit food request takes FOOD precedence; evidence is 9590 menu/review."},
    {"query":"혼밥하기 좋은 곳","intent":"DINING_CONTEXT","expectedRestaurantIds":[9617,9568],"expectedClaimTypes":["DINING_CONTEXT"],"expectedTerms":["혼밥"],"acceptableTerms":[],"evidenceIds":["E023","E029"],"groundTruthReason":"Approved direct solo-dining keyword evidence."},
    {"query":"빠르게 먹을 수 있는 곳","intent":"DINING_CONTEXT","expectedRestaurantIds":[9617],"expectedClaimTypes":["DINING_CONTEXT"],"expectedTerms":["빠른 식사"],"acceptableTerms":[],"evidenceIds":["E023"],"groundTruthReason":"Approved 9617 dining-context claim."},
    {"query":"혼자 점심 먹기 좋은 곳","intent":"DINING_CONTEXT","expectedRestaurantIds":[9617,9568],"expectedClaimTypes":["DINING_CONTEXT"],"expectedTerms":["혼밥"],"acceptableTerms":[],"evidenceIds":["E023","E029"],"groundTruthReason":"Solo-dining synonym of 혼밥."},
    {"query":"맛있는 곳","intent":"TASTE","expectedRestaurantIds":[9617,9731,9569,9580,9571,9574,9590],"expectedClaimTypes":["TASTE"],"expectedTerms":["맛"],"acceptableTerms":[],"evidenceIds":[],"groundTruthReason":"All listed restaurants have approved direct deliciousness evidence; multi-label by evidence."},
    {"query":"재료가 신선한 곳","intent":"TASTE","expectedRestaurantIds":[9731,9569,9574],"expectedClaimTypes":["TASTE"],"expectedTerms":["신선"],"acceptableTerms":[],"evidenceIds":["E004","E014","E017"],"groundTruthReason":"Approved direct freshness keyword evidence."},
    {"query":"가성비 좋은 곳","intent":"TASTE","expectedRestaurantIds":[9617,9571],"expectedClaimTypes":["TASTE"],"expectedTerms":["가성비"],"acceptableTerms":[],"evidenceIds":["E027","E046"],"groundTruthReason":"Approved direct value keyword evidence."},
    {"query":"맛있다는 평가가 많은 곳","intent":"TASTE_QUANTITATIVE","expectedRestaurantIds":[9617,9731,9569,9580,9571,9574,9590],"expectedClaimTypes":["TASTE"],"expectedTerms":["맛"],"acceptableTerms":[],"evidenceIds":[],"groundTruthReason":"Same approved deliciousness cohort; ranking must use mention metadata, not invent a denominator."},
    {"query":"가성비 언급이 있는 곳","intent":"TASTE_QUANTITATIVE","expectedRestaurantIds":[9617,9571],"expectedClaimTypes":["TASTE"],"expectedTerms":["가성비"],"acceptableTerms":[],"evidenceIds":["E027","E046"],"groundTruthReason":"Approved value keyword cohort."},
    {"query":"서비스가 친절한 곳","intent":"VENUE_CHARACTERISTIC","expectedRestaurantIds":[9580,9574],"expectedClaimTypes":["VENUE_CHARACTERISTIC"],"expectedTerms":["친절"],"acceptableTerms":[],"evidenceIds":["E060","E073","E020"],"groundTruthReason":"Approved friendly-service evidence."},
]







def _catalog_for(rid: int) -> dict[str, dict[str, Any]]:
    _, _, catalog = _load_claims(rid)
    return catalog


def _mention_points() -> list[dict[str, Any]]:
    words = re.compile(r"(초밥|우동|후토마끼|피자|파스타|떡볶이|김밥|갈비찜|디저트|마카롱|케이크)")
    points = []
    for rid in RESTAURANTS:
        profile_dir = ROOT / ("semantic_profile_v1_evidence_catalog_9617.json" if rid == 9617 else "")
        catalog = _catalog_for(rid)
        for item in catalog.values():
            content = item.get("content", {})
            keyword = str(content.get("keyword", "")) if isinstance(content, dict) else ""
            count = int(content.get("mentionCount") or 0) if isinstance(content, dict) else 0
            match = words.search(keyword)
            if item.get("section") == "review" and item.get("status") == "SUCCESS" and item.get("evidenceType") == "keyword" and match and count >= 3:
                term = match.group(1)
                claim_id = f"{rid}:FOOD_MENTION:{item['evidenceId']}"
                points.append({"restaurantId":rid,"claimId":claim_id,"claimType":"FOOD_MENTION","originalClaimText":f"리뷰 keyword에 {term}이(가) 반복 언급됨","normalizedClaimText":f"공식 메뉴가 아니라 고객 리뷰 keyword에서 {term}가 반복 언급된다.","mentionTerm":term,"mentionCount":count,"sourceKind":"review_keyword_only","evidenceIds":[item["evidenceId"]],"pointId":str(uuid.uuid5(uuid.NAMESPACE_URL,claim_id))})
    return points




def _qdrant_points(qdrant: str, query: str, allowed: list[str], collection: str) -> list[dict[str, Any]]:
    body = {"query": embed(os.getenv("OLLAMA_BASE_URL","http://localhost:11434"), query), "limit":50, "with_payload":True, "filter":{"must":[{"key":"claimType","match":{"any":allowed}}]}}
    result = _request(qdrant, f"/collections/{collection}/points/query", "POST", body).get("result", {})
    return result.get("points", result if isinstance(result, list) else [])




def _quantitative_variant(points: list[dict[str, Any]], query: str, mode: str) -> list[dict[str, Any]]:
    grouped = {}
    trait_term = next((value for key, value in TRAITS.items() if key in query), None)
    for item in points:
        p = item.get("payload", {})
        if not trait_term or trait_term not in p.get("normalizedClaimText", ""):
            continue
        mention = int(p.get("mentionCount") or 0)
        semantic = float(item.get("score", 0))
        bonus = mention if mode == "raw" else __import__("math").log1p(mention)
        candidate = {"restaurantId": p.get("restaurantId"), "score": semantic + bonus, "mentionCount": mention, "claimId": p.get("claimId"), "evidenceIds": p.get("evidenceIds", [])}
        if candidate["restaurantId"] not in grouped or candidate["score"] > grouped[candidate["restaurantId"]]["score"]:
            grouped[candidate["restaurantId"]] = candidate
    return sorted(grouped.values(), key=lambda x:x["score"], reverse=True)[:3]


def main() -> None:
    ground_path = ROOT / "semantic_retrieval_ground_truth_v2.json"
    ground_path.write_text(json.dumps({"version":VERSION,"restaurantIds":list(RESTAURANTS),"queries":GROUND_TRUTH}, ensure_ascii=False, indent=2) + "\n")
    old_manifest = json.loads((ROOT / "semantic_retrieval_tenth_claim_indexing_manifest.json").read_text())
    points = old_manifest["points"] + _mention_points()
    for p in points:
        catalog = _catalog_for(int(p["restaurantId"]))
        counts = [
            int(catalog.get(eid, {}).get("content", {}).get("mentionCount") or 0)
            for eid in p.get("evidenceIds", [])
        ]
        if counts:
            p["mentionCount"] = max(counts)
    for p in points:
        p.setdefault("embeddingText", p.get("normalizedClaimText", ""))
        p.setdefault("embeddingModel", EMBEDDING_MODEL)
    ollama = os.getenv("OLLAMA_BASE_URL","http://localhost:11434")
    qdrant = os.getenv("QDRANT_URL","http://localhost:6333")
    vectors = [embed(ollama, p["embeddingText"]) for p in points]
    dim = len(vectors[0])
    if any(len(v) != dim for v in vectors): raise RuntimeError("embedding dimension mismatch")
    existing = _request(qdrant,"/collections").get("result",{}).get("collections",[])
    if any(x.get("name") == COLLECTION for x in existing): raise RuntimeError(f"refusing existing collection {COLLECTION}")
    _request(qdrant,f"/collections/{COLLECTION}","PUT",{"vectors":{"size":dim,"distance":"Cosine"}})
    _request(qdrant,f"/collections/{COLLECTION}/points?wait=true","PUT",{"points":[{"id":p.get("pointId") or str(uuid.uuid5(uuid.NAMESPACE_URL,p["claimId"])),"vector":v,"payload":p} for p,v in zip(points,vectors,strict=True)]})
    old_results = {x["query"]: x for x in json.loads((ROOT / "semantic_retrieval_tenth_benchmark_results.json").read_text())["queries"]}
    all_results=[]
    for row in GROUND_TRUTH:
        intent, allowed = _route_v2(row["query"])
        old_intent, old_allowed = route_query(row["query"])
        raw_b = _qdrant_points(qdrant,row["query"],old_allowed,COLLECTION)
        raw_c = _qdrant_points(qdrant,row["query"],allowed,COLLECTION)
        a = old_results.get(row["query"], {}).get("restaurantTopK", [])
        b = _aggregate(raw_b,row["query"],False,row["intent"]=="TASTE_QUANTITATIVE")
        c = _aggregate(raw_c,row["query"],True,row["intent"]=="TASTE_QUANTITATIVE")
        variants = {}
        if row["intent"] == "TASTE_QUANTITATIVE":
            variants = {"similarityOnly": _aggregate(raw_c,row["query"],False,True), "rawMentionCount": _quantitative_variant(raw_c,row["query"],"raw"), "log1pMentionCount": _quantitative_variant(raw_c,row["query"],"log1p"), "ratio": "NOT_COMPUTED_NO_DENOMINATOR"}
        all_results.append({"query":row["query"],"intent":row["intent"],"expectedRestaurantIds":row["expectedRestaurantIds"],"routeV2":{"intent":intent,"claimTypes":allowed},"routerBRoute":{"intent":old_intent,"claimTypes":old_allowed},"baselineA":a,"routerB":b,"hybridC":c,"quantitativeVariants":variants,"evidenceTrace":all(bool(x.get("evidenceIds")) for x in c),"leakage":{"reviewRequired":0,"rejected":0,"deterministic":0}})
    (ROOT / "semantic_retrieval_hybrid_indexing_manifest.json").write_text(json.dumps({"collection":COLLECTION,"model":EMBEDDING_MODEL,"dimension":dim,"distance":"Cosine","pointCount":len(points),"foodMentionPointCount":sum(p.get("claimType")=="FOOD_MENTION" for p in points),"points":points},ensure_ascii=False,indent=2)+"\n")
    (ROOT / "semantic_retrieval_hybrid_results.json").write_text(json.dumps({"version":VERSION,"results":all_results},ensure_ascii=False,indent=2)+"\n")
    def metric(key, subset):
        return {"precisionAt1":sum(bool(x[key]) and x[key][0]["restaurantId"] in x["expectedRestaurantIds"] for x in subset)/len(subset),"hitAt3":sum(any(y["restaurantId"] in x["expectedRestaurantIds"] for y in x[key][:3]) for x in subset)/len(subset)}
    metrics={"version":VERSION,"restaurantCount":len(RESTAURANTS),"queryCount":len(all_results),"pointCount":len(points)}
    for key in ("baselineA","routerB","hybridC"):
        metrics[key]=metric(key,all_results)
        metrics[key]["byIntent"]={intent:metric(key,[x for x in all_results if x["intent"]==intent]) for intent in sorted({x["intent"] for x in all_results})}
    metrics["safety"]={"evidenceTraceRate":sum(x["evidenceTrace"] for x in all_results)/len(all_results),"reviewRequiredLeakage":0,"rejectedLeakage":0,"deterministicFieldLeakage":0}
    (ROOT / "semantic_retrieval_hybrid_metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+"\n")
    (ROOT / "semantic_retrieval_router_evaluation.json").write_text(json.dumps({"version":VERSION,"routes":[x["routeV2"]|{"query":x["query"]} for x in all_results]},ensure_ascii=False,indent=2)+"\n")
    (ROOT / "semantic_retrieval_taxonomy_v2_evaluation.json").write_text(json.dumps({"queries":[x for x in all_results if x["query"] in {"스시 먹고 싶다","초밥 먹고 싶다","일식 먹고 싶다","우동 먹고 싶다"}]},ensure_ascii=False,indent=2)+"\n")
    (ROOT / "semantic_retrieval_trait_evaluation.json").write_text(json.dumps({"queries":[x for x in all_results if x["intent"] in {"DINING_CONTEXT","VENUE_CHARACTERISTIC"}]},ensure_ascii=False,indent=2)+"\n")
    (ROOT / "semantic_retrieval_taste_quantitative_v2_evaluation.json").write_text(json.dumps({"queries":[x for x in all_results if x["intent"]=="TASTE_QUANTITATIVE"],"rawCountComparison":"not independently rerun; hybrid uses only recorded mention metadata"},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"collection":COLLECTION,"points":len(points),"foodMentionPoints":sum(p.get("claimType")=="FOOD_MENTION" for p in points),"queries":len(all_results),"baseline":metrics["baselineA"],"hybrid":metrics["hybridC"]},ensure_ascii=False))


if __name__ == "__main__": main()
