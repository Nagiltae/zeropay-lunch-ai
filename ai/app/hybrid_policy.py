"""Shared offline/runtime hybrid policy; no database or artifact access."""

import re
from typing import Any

FOOD_TERM_MAP = {
    "스시": ["초밥"],
    "초밥": ["초밥"],
    "우동": ["우동"],
    "후토마끼": ["후토마끼"],
    "일식": ["초밥", "우동", "후토마끼"],
    "피자": ["피자"],
    "파스타": ["파스타"],
    "떡볶이": ["떡볶이"],
    "김밥": ["김밥"],
    "갈비찜": ["갈비찜"],
    "한식": ["한식", "순대국", "된장찌개", "갈비찜"],
    "한정식": ["정식", "갈비찜"],
    "디저트": ["디저트", "케이크", "마카롱"],
}


TRAITS = {
    "혼밥": "혼밥",
    "빠르게": "빠른 식사",
    "맛있는": "맛",
    "신선": "신선",
    "가성비": "가성비",
    "친절": "친절",
    "평가가 많은": "맛",
    "언급이 있는": "가성비",
}


def _route_v2(query: str) -> tuple[str, list[str]]:
    if re.search(
        r"먹고 싶|메뉴가|디저트|피자|파스타|떡볶이|김밥|갈비찜|한식|한정식|스시|초밥|일식|우동|후토마끼",
        query,
    ):
        return "FOOD", ["FOOD_TYPE", "FOOD_MENTION", "MENU_CHARACTERISTIC"]
    if re.search(r"혼밥|빠르|단체|회식|혼자 점심", query):
        return "DINING_CONTEXT", ["DINING_CONTEXT"]
    if re.search(r"평가가 많은|언급이 많|언급이 있는|리뷰가 많은", query):
        return "TASTE_QUANTITATIVE", ["TASTE"]
    if re.search(r"맛있|가성비|신선", query):
        return "TASTE", ["TASTE"]
    if re.search(r"친절|서비스|분위기|넓", query):
        return "VENUE_CHARACTERISTIC", ["VENUE_CHARACTERISTIC"]
    return "UNKNOWN", ["FOOD_TYPE", "FOOD_MENTION", "MENU_CHARACTERISTIC"]


def _food_terms(query: str) -> tuple[list[str], list[str], list[str]]:
    exact = [key for key in FOOD_TERM_MAP if key in query and key not in {"일식", "한식", "한정식"}]
    synonym = []
    category = []
    if "스시" in query:
        synonym = ["초밥"]
    if "일식" in query:
        category = FOOD_TERM_MAP["일식"]
    if "한식" in query or "한정식" in query:
        category = FOOD_TERM_MAP["한식" if "한식" in query else "한정식"]
    terms = list(dict.fromkeys(exact + synonym + category))
    return exact, synonym, terms


def _lexical(point: dict[str, Any], query: str) -> tuple[int, int, int, bool, bool, bool, int]:
    exact, synonym, all_terms = _food_terms(query)
    text = f"{point.get('normalizedClaimText', '')} {point.get('mentionTerm', '')}"
    exact_hit = any(t in text for t in exact)
    synonym_hit = not exact_hit and any(t in text for t in synonym)
    category_hit = not exact_hit and not synonym_hit and any(t in text for t in all_terms)
    source = 2 if point.get("claimType") in {"FOOD_TYPE", "MENU_CHARACTERISTIC"} else 1
    tier = 3 if exact_hit else 2 if synonym_hit else 1 if category_hit else 0
    mention = int(point.get("mentionCount") or 0)
    return tier, source, mention, exact_hit, synonym_hit, category_hit, mention


def _aggregate(
    points: list[dict[str, Any]],
    query: str,
    hybrid: bool,
    quantitative: bool = False,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    grouped = {}
    for item in points:
        p = item.get("payload", {})
        tier, source, mention, exact, synonym, category, _ = _lexical(p, query)
        trait_term = next((value for key, value in TRAITS.items() if key in query), None)
        trait = tier > 0 or bool(trait_term and trait_term in p.get("normalizedClaimText", ""))
        if quantitative and not trait:
            continue
        semantic = float(item.get("score", 0))
        if hybrid:
            score = (
                tier * 100
                + source * 10
                + (min(mention, 999) if quantitative else 0) / 1000
                + semantic / 1000
            )
        else:
            score = semantic
        candidate = {
            "restaurantId": p.get("restaurantId"),
            "finalRetrievalScore": score,
            "matchedClaimId": p.get("claimId"),
            "matchedClaimType": p.get("claimType"),
            "matchedClaimText": p.get("normalizedClaimText") or p.get("originalClaimText"),
            "semanticScore": semantic,
            "exactMatch": exact,
            "synonymMatch": synonym,
            "categoryMatch": category,
            "traitMatch": trait,
            "mentionCount": mention,
            "evidenceIds": p.get("evidenceIds", []),
        }
        if (
            p.get("restaurantId") not in grouped
            or score > grouped[p.get("restaurantId")]["finalRetrievalScore"]
        ):
            grouped[p.get("restaurantId")] = candidate
    return sorted(grouped.values(), key=lambda x: x["finalRetrievalScore"], reverse=True)[:top_k]
