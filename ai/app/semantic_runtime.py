"""Internal HTTP contract services. No MySQL access and no indexing operations."""

import math
import os
import re
from typing import Annotated, Literal
from urllib.error import URLError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.hybrid_policy import FOOD_TERM_MAP, _aggregate, _route_v2
from app.semantic_embedding_qdrant_pilot import _request, embed

Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
RestaurantId = Annotated[int, Field(strict=True, gt=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntentRequest(Contract):
    query: Query


class IntentResponse(Contract):
    intent: str = "RESTAURANT_RECOMMENDATION"
    foodTerms: list[str]
    diningContexts: list[str]
    tasteTraits: list[str]
    maxBudget: int | None
    quantitativeTaste: bool
    primaryIntent: str
    claimTypes: list[str]


class RetrievalRequest(IntentRequest):
    candidateRestaurantIds: list[RestaurantId] = Field(max_length=1000)
    topK: Annotated[int, Field(strict=True, ge=1, le=100)] = 10


class MatchedClaim(Contract):
    claimId: str
    claimType: str
    claimText: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    semanticSimilarity: float = Field(allow_inf_nan=False)
    matchType: Literal["EXACT", "SYNONYM", "CATEGORY", "TRAIT", "SEMANTIC"]
    exactMatch: bool
    synonymMatch: bool
    categoryMatch: bool
    traitMatch: bool
    mentionCount: int | None
    evidenceIds: list[str] = Field(min_length=1)


class Candidate(Contract):
    restaurantId: RestaurantId
    retrievalScore: float = Field(allow_inf_nan=False)
    semanticSimilarity: float = Field(allow_inf_nan=False)
    matchedClaims: list[MatchedClaim]


class RetrievalResponse(Contract):
    candidates: list[Candidate]
    policyVersion: str = "hybrid-v2-capped-count"


class DependencyUnavailable(RuntimeError):
    pass


def analyze(query: str) -> IntentResponse:
    primary, types = _route_v2(query)
    contexts = []
    if re.search(r"혼밥|혼자", query):
        contexts.append("SOLO_DINING")
    if re.search(r"빠르|빠른|빨리", query):
        contexts.append("QUICK_MEAL")
    if re.search(r"단체|회식", query):
        contexts.append("GROUP_DINING")
    traits = [
        value
        for term, value in (
            ("맛있", "DELICIOUS"),
            ("신선", "FRESH_INGREDIENT"),
            ("가성비", "GOOD_VALUE"),
            ("친절", "FRIENDLY_SERVICE"),
        )
        if term in query
    ]
    amount = re.search(r"(?<![\d.])([\d,]+(?:\.\d+)?)\s*(만)?\s*원", query)
    budget = None
    if amount:
        value = float(amount[1].replace(",", "")) * (10000 if amount[2] else 1)
        if 0 < value <= 100000000 and value.is_integer():
            budget = int(value)
    return IntentResponse(
        foodTerms=[t for t in FOOD_TERM_MAP if t in query],
        diningContexts=contexts,
        tasteTraits=traits,
        maxBudget=budget,
        quantitativeTaste=primary == "TASTE_QUANTITATIVE",
        primaryIntent=primary,
        claimTypes=types,
    )


class SemanticRetrievalService:
    def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        if not request.candidateRestaurantIds:
            return RetrievalResponse(candidates=[])
        collection = os.getenv("QDRANT_SEMANTIC_COLLECTION", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", collection):
            raise DependencyUnavailable("collection configuration missing")
        scope = sorted(set(request.candidateRestaurantIds))
        intent = analyze(request.query)
        try:
            vector = embed(
                os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), request.query, timeout=3.0
            )
            if len(vector) != 1024 or any(not math.isfinite(x) for x in vector):
                raise ValueError("invalid vector")
            result = _request(
                os.getenv("QDRANT_URL", "http://localhost:6333"),
                f"/collections/{collection}/points/query",
                "POST",
                {
                    "query": vector,
                    "limit": 200,
                    "with_payload": True,
                    "filter": {
                        "must": [
                            {"key": "restaurantId", "match": {"any": scope}},
                            {"key": "claimType", "match": {"any": intent.claimTypes}},
                        ]
                    },
                },
                timeout=3.0,
            )
            points = result["result"]["points"]
            # Treat a malformed/out-of-scope dependency response as unavailable.
            for item in points:
                payload = item["payload"]
                if (
                    payload["restaurantId"] not in scope
                    or payload["claimType"] not in intent.claimTypes
                    or not payload.get("evidenceIds")
                    or not payload.get("claimId")
                    or not math.isfinite(item["score"])
                ):
                    raise ValueError("invalid scoped payload")
            ranked = _aggregate(points, request.query, True, intent.quantitativeTaste, request.topK)
            candidates = []
            for row in ranked:
                relation = next(
                    (
                        name
                        for field, name in (
                            ("exactMatch", "EXACT"),
                            ("synonymMatch", "SYNONYM"),
                            ("categoryMatch", "CATEGORY"),
                            ("traitMatch", "TRAIT"),
                        )
                        if row[field]
                    ),
                    "SEMANTIC",
                )
                claim = MatchedClaim(
                    claimId=row["matchedClaimId"],
                    claimType=row["matchedClaimType"],
                    claimText=row["matchedClaimText"],
                    semanticSimilarity=row["semanticScore"],
                    matchType=relation,
                    exactMatch=row["exactMatch"],
                    synonymMatch=row["synonymMatch"],
                    categoryMatch=row["categoryMatch"],
                    traitMatch=row["traitMatch"],
                    mentionCount=row["mentionCount"],
                    evidenceIds=row["evidenceIds"],
                )
                candidates.append(
                    Candidate(
                        restaurantId=row["restaurantId"],
                        retrievalScore=row["finalRetrievalScore"],
                        semanticSimilarity=row["semanticScore"],
                        matchedClaims=[claim],
                    )
                )
            return RetrievalResponse(candidates=candidates)
        except (URLError, OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            raise DependencyUnavailable("semantic dependency failed") from error


def retrieve_explanation_claims(
    query: str, restaurant_ids: list[int], claim_types: list[str]
) -> list[dict]:
    """Return raw, evidence-bearing claims only within the already-final restaurant scope."""
    if not restaurant_ids or not claim_types:
        return []
    collection = os.getenv("QDRANT_SEMANTIC_COLLECTION", "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", collection):
        raise DependencyUnavailable("collection configuration missing")
    allowed_ids = set(restaurant_ids)
    allowed_types = set(claim_types)
    try:
        vector = embed(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), query, timeout=3.0)
        if len(vector) != 1024 or any(not math.isfinite(value) for value in vector):
            raise ValueError("invalid query embedding")
        response = _request(
            os.getenv("QDRANT_URL", "http://localhost:6333"),
            f"/collections/{collection}/points/query",
            "POST",
            {
                "query": vector,
                "limit": 200,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "restaurantId", "match": {"any": sorted(allowed_ids)}},
                        {"key": "claimType", "match": {"any": sorted(allowed_types)}},
                    ]
                },
            },
            timeout=3.0,
        )
        claims = []
        seen = set()
        for point in response["result"]["points"]:
            payload = point["payload"]
            restaurant_id = payload["restaurantId"]
            claim_type = payload["claimType"]
            evidence_ids = payload.get("evidenceIds")
            claim_id = payload.get("claimId")
            claim_text = payload.get("originalClaimText") or payload.get("normalizedClaimText")
            if (
                restaurant_id not in allowed_ids
                or claim_type not in allowed_types
                or not claim_id
                or not isinstance(claim_text, str)
                or not claim_text.strip()
                or not isinstance(evidence_ids, list)
                or not evidence_ids
                or not all(isinstance(value, str) and value for value in evidence_ids)
                or not math.isfinite(point["score"])
            ):
                raise ValueError("invalid explanation evidence payload")
            if claim_id in seen:
                continue
            seen.add(claim_id)
            claims.append({
                "restaurantId": restaurant_id,
                "claimId": claim_id,
                "claimType": claim_type,
                "text": claim_text,
                "matchType": "TRAIT",
                "evidenceIds": evidence_ids,
            })
        return claims
    except (URLError, OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        raise DependencyUnavailable("explanation evidence dependency failed") from error
