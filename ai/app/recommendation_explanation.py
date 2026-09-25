"""Bounded, evidence-grounded explanations for Spring-selected recommendations."""

from __future__ import annotations

import json
import os
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from app.entity_resolution.qwen_candidate_matcher import OllamaClient, configured_qwen_model
from app.hybrid_policy import FOOD_TERM_MAP
from app.semantic_runtime import analyze, retrieve_explanation_claims

ExplanationText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]
EvidenceId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExplanationClaim(StrictContract):
    claimType: Literal[
        "FOOD_TYPE", "FOOD_MENTION", "MENU_CHARACTERISTIC", "TASTE",
        "DINING_CONTEXT", "VENUE_CHARACTERISTIC",
    ]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    matchType: Literal["EXACT", "SYNONYM", "CATEGORY", "TRAIT", "SEMANTIC"]
    evidenceIds: list[EvidenceId] = Field(min_length=1, max_length=10)


class DeterministicFacts(StrictContract):
    zeroPayAvailable: bool
    budgetMatched: bool | None = None


class ExplanationRestaurant(StrictContract):
    restaurantId: Annotated[int, Field(strict=True, gt=0)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    matchedClaims: list[ExplanationClaim] = Field(max_length=10)
    deterministicFacts: DeterministicFacts


class ExplanationRequest(StrictContract):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    restaurants: list[ExplanationRestaurant] = Field(min_length=1, max_length=3)
    useLlm: bool = False

    @model_validator(mode="after")
    def restaurant_ids_are_unique(self):
        ids = [restaurant.restaurantId for restaurant in self.restaurants]
        if len(ids) != len(set(ids)):
            raise ValueError("restaurant ids must be unique")
        return self


class SafeFact(StrictContract):
    evidenceIds: list[EvidenceId] = Field(min_length=1, max_length=10)
    factType: Literal["FOOD", "FOOD_MENTION", "DINING_CONTEXT", "TASTE", "VENUE_CHARACTERISTIC"]
    fact: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class GeneratedExplanation(StrictContract):
    restaurantId: Annotated[int, Field(strict=True, gt=0)]
    explanation: ExplanationText
    usedEvidenceIds: list[EvidenceId] = Field(min_length=1, max_length=10)


class GeneratedOutput(StrictContract):
    explanations: list[GeneratedExplanation] = Field(min_length=1, max_length=3)


class ExplanationItem(StrictContract):
    restaurantId: Annotated[int, Field(strict=True, gt=0)]
    explanation: ExplanationText
    usedEvidenceIds: list[EvidenceId]
    availableEvidenceIds: list[EvidenceId]
    source: Literal["LLM", "DETERMINISTIC_FALLBACK"]


class ExplanationResponse(StrictContract):
    explanations: list[ExplanationItem] = Field(min_length=1, max_length=3)


class CompletionClient(Protocol):
    def complete(self, system: str, user: str, response_schema: dict) -> str: ...


class ExplanationEvidenceRetriever(Protocol):
    def retrieve(self, query: str, restaurant_ids: list[int], claim_types: list[str]) -> list[dict]: ...


SYSTEM_PROMPT = """/no_think
너는 사실을 추론하는 모델이 아니라 제공된 Safe Facts를 문장으로 조합하는 작성기다.
Spring이 이미 선택한 식당의 opaque ID별로, 전달된 fact만 사용해 자연스러운 한국어 한 문장을 작성하라.
새로운 메뉴, 재료, 평가, 이용 맥락 또는 장소 특성을 추론하지 마라.
결제 방식, 제로페이, 가격, 예산, 영업시간, 위치, 거리, 인기, 평점은 절대 언급하지 마라.
식당을 선택하거나 추가/삭제/재정렬하지 마라. 입력 ID와 Evidence ID를 그대로 보존하라.
반드시 JSON Schema에 맞는 JSON만 반환하라."""

_FORBIDDEN_UNSUPPORTED = (
    "인기", "평점", "별점", "근처", "가까", "저렴", "최저가", "조용", "최고", "유명", "넓",
    "가격", "무료", "무상", "공짜", "무비자", "비자 결제", "제로페이", "결제", "예산",
    "영업시간", "영업 중", "영업중",
)
_SEMANTIC_MARKERS = tuple(dict.fromkeys(
    list(FOOD_TERM_MAP)
    + [term for terms in FOOD_TERM_MAP.values() for term in terms]
    + ["혼밥", "혼자", "빠른 식사", "빠르게", "단체", "회식", "가성비", "신선", "맛있", "친절"]
))


class RecommendationExplanationService:
    def __init__(
        self,
        client: CompletionClient | None,
        evidence_retriever: ExplanationEvidenceRetriever | None = None,
        llm_enabled: bool = False,
    ):
        self.client = client
        self.evidence_retriever = evidence_retriever
        self.llm_enabled = llm_enabled

    def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        claims_by_id = {restaurant.restaurantId: list(restaurant.matchedClaims) for restaurant in request.restaurants}
        if self.evidence_retriever is not None:
            intent = analyze(request.query)
            requested_types = list(intent.claimTypes)
            if intent.diningContexts:
                requested_types.append("DINING_CONTEXT")
            if intent.tasteTraits:
                requested_types.append("TASTE")
            requested_types = list(dict.fromkeys(requested_types))
            try:
                supplemental = self.evidence_retriever.retrieve(
                    request.query, [restaurant.restaurantId for restaurant in request.restaurants], requested_types
                )
                for claim in supplemental:
                    restaurant_id = claim["restaurantId"]
                    if restaurant_id not in claims_by_id:
                        continue
                    claims_by_id[restaurant_id].append(ExplanationClaim(
                        claimType=claim["claimType"], text=claim["text"],
                        matchType=claim["matchType"], evidenceIds=claim["evidenceIds"],
                    ))
            except (RuntimeError, ValueError, TypeError, KeyError):
                # Keep Spring-supplied evidence usable if this bounded supplement is unavailable.
                pass

        safe_facts = {
            restaurant.restaurantId: _safe_facts(request.query, claims_by_id[restaurant.restaurantId])
            for restaurant in request.restaurants
        }
        if not (self.llm_enabled and request.useLlm):
            return _fallback_response(request, safe_facts)
        if self.client is None:
            return _fallback_response(request, safe_facts)
        evidenced = [restaurant for restaurant in request.restaurants if safe_facts[restaurant.restaurantId]]
        if not evidenced:
            return _fallback_response(request, safe_facts)
        try:
            payload = {
                "query": request.query,
                "restaurants": [
                    {
                        "restaurantId": restaurant.restaurantId,
                        "facts": [fact.model_dump(mode="json") for fact in safe_facts[restaurant.restaurantId]],
                    }
                    for restaurant in evidenced
                ],
            }
            output = self.client.complete(
                SYSTEM_PROMPT,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                _output_schema(),
            )
            generated = GeneratedOutput.model_validate_json(output)
            _validate_grounding(generated, evidenced, safe_facts)
            generated_by_id = {item.restaurantId: item for item in generated.explanations}
            items = []
            for restaurant in request.restaurants:
                generated_item = generated_by_id.get(restaurant.restaurantId)
                if generated_item is None:
                    items.append(_fallback_item(restaurant, safe_facts[restaurant.restaurantId]))
                else:
                    items.append(ExplanationItem(
                        restaurantId=generated_item.restaurantId,
                        explanation=generated_item.explanation,
                        usedEvidenceIds=generated_item.usedEvidenceIds,
                        availableEvidenceIds=_evidence_ids(safe_facts[restaurant.restaurantId]),
                        source="LLM",
                    ))
            return ExplanationResponse(explanations=items)
        except (TimeoutError, OSError, RuntimeError, ValueError, ValidationError, TypeError):
            return _fallback_response(request, safe_facts)


def _safe_facts(query: str, claims: list[ExplanationClaim]) -> list[SafeFact]:
    facts: list[SafeFact] = []
    exact_terms: list[str] = []
    for query_term, equivalents in FOOD_TERM_MAP.items():
        if query_term in query:
            exact_terms.extend([query_term, *equivalents])
    exact_terms = list(dict.fromkeys(exact_terms))
    dining = (
        ("혼밥", "혼밥하기 좋다는 고객 평가가 확인됨"),
        ("혼자", "혼자 식사하기 좋다는 고객 평가가 확인됨"),
        ("빠르", "빠르게 식사하기 좋다는 고객 평가가 확인됨"),
        ("단체", "단체 이용에 대한 고객 평가가 확인됨"),
        ("회식", "회식 이용에 대한 고객 평가가 확인됨"),
    )
    taste = (
        (("가성비", "good value"), "가성비가 좋다는 고객 평가가 확인됨"),
        (("신선", "fresh ingredient"), "재료가 신선하다는 고객 평가가 확인됨"),
        (("맛있", "delicious", "tasty"), "음식이 맛있다는 고객 평가가 확인됨"),
        (("친절", "friendly service"), "친절한 서비스라는 고객 평가가 확인됨"),
    )
    for claim in claims:
        text = claim.text.lower()
        if claim.claimType in {"FOOD_TYPE", "FOOD_MENTION", "MENU_CHARACTERISTIC"}:
            term = next((term for term in exact_terms if term.lower() in text), None)
            if term is None:
                continue
            if claim.claimType == "FOOD_MENTION":
                facts.append(SafeFact(
                    evidenceIds=claim.evidenceIds, factType="FOOD_MENTION",
                    fact=f"고객 리뷰에서 {term} 관련 언급이 확인됨",
                ))
            else:
                facts.append(SafeFact(
                    evidenceIds=claim.evidenceIds, factType="FOOD",
                    fact=f"{term} 메뉴가 확인됨",
                ))
        elif claim.claimType == "DINING_CONTEXT":
            fact = next((fact for term, fact in dining if term in query and term in text), None)
            if fact:
                facts.append(SafeFact(evidenceIds=claim.evidenceIds, factType="DINING_CONTEXT", fact=fact))
        elif claim.claimType in {"TASTE", "VENUE_CHARACTERISTIC"}:
            fact = next((fact for terms, fact in taste if any(term in query.lower() and term in text for term in terms)), None)
            if fact:
                facts.append(SafeFact(
                    evidenceIds=claim.evidenceIds,
                    factType="VENUE_CHARACTERISTIC" if claim.claimType == "VENUE_CHARACTERISTIC" else "TASTE",
                    fact=fact,
                ))
    unique: dict[tuple[str, str], SafeFact] = {}
    for fact in facts:
        unique.setdefault((fact.factType, fact.fact), fact)
    result = list(unique.values())
    official_terms = {
        term for fact in result if fact.factType == "FOOD"
        for term in exact_terms if term in fact.fact
    }
    result = [
        fact for fact in result
        if fact.factType != "FOOD_MENTION"
        or not any(term in fact.fact for term in official_terms)
    ]
    return result[:10]


def _validate_grounding(
    output: GeneratedOutput,
    restaurants: list[ExplanationRestaurant],
    safe_facts: dict[int, list[SafeFact]],
) -> None:
    expected_ids = [restaurant.restaurantId for restaurant in restaurants]
    actual_ids = [item.restaurantId for item in output.explanations]
    if actual_ids != expected_ids:
        raise ValueError("explanation restaurant identity/order mismatch")
    for item, restaurant in zip(output.explanations, restaurants, strict=True):
        allowed = {evidence_id for fact in safe_facts[restaurant.restaurantId] for evidence_id in fact.evidenceIds}
        if not item.usedEvidenceIds or not set(item.usedEvidenceIds).issubset(allowed):
            raise ValueError("explanation cites evidence outside its restaurant context")
        if any(term in item.explanation for term in _FORBIDDEN_UNSUPPORTED):
            raise ValueError("explanation contains unsupported assertion")
        allowed_text = " ".join(fact.fact for fact in safe_facts[restaurant.restaurantId])
        if any(term in item.explanation and term not in allowed_text for term in _SEMANTIC_MARKERS):
            raise ValueError("explanation introduces a semantic fact absent from safe facts")
        if any(char.isdigit() for char in item.explanation):
            raise ValueError("explanation contains ungrounded numeric detail")


def _fallback_text(facts: list[SafeFact]) -> str:
    if not facts:
        return "요청 조건과 관련된 추천 정보가 확인됐어요."
    phrases = [fact.fact for fact in facts]
    if len(phrases) == 1:
        phrase = phrases[0]
        if facts[0].factType == "FOOD":
            return phrase.removesuffix(" 확인됨") + " 확인되어 추천했어요."
        if facts[0].factType == "FOOD_MENTION":
            return phrase.removesuffix(" 확인됨") + " 있어 추천했어요."
        return phrase.removesuffix(" 확인됨") + " 확인돼 추천했어요."
    first = phrases[0].removesuffix(" 확인됨") + " 확인되고"
    remainder = [phrase.removesuffix(" 확인됨") + " 확인돼" for phrase in phrases[1:]]
    return " ".join([first, *remainder]) + " 추천했어요."


def _fallback_item(restaurant: ExplanationRestaurant, facts: list[SafeFact]) -> ExplanationItem:
    evidence_ids = _evidence_ids(facts)
    return ExplanationItem(
        restaurantId=restaurant.restaurantId,
        explanation=_fallback_text(facts),
        usedEvidenceIds=evidence_ids,
        availableEvidenceIds=evidence_ids,
        source="DETERMINISTIC_FALLBACK",
    )


def _evidence_ids(facts: list[SafeFact]) -> list[str]:
    return list(dict.fromkeys(evidence_id for fact in facts for evidence_id in fact.evidenceIds))[:100]


def _fallback_response(
    request: ExplanationRequest, facts_by_id: dict[int, list[SafeFact]] | None = None
) -> ExplanationResponse:
    facts_by_id = facts_by_id or {restaurant.restaurantId: [] for restaurant in request.restaurants}
    return ExplanationResponse(explanations=[
        _fallback_item(restaurant, facts_by_id[restaurant.restaurantId]) for restaurant in request.restaurants
    ])


def _output_schema() -> dict:
    return GeneratedOutput.model_json_schema()


class FinalCandidateEvidenceRetriever:
    def retrieve(self, query: str, restaurant_ids: list[int], claim_types: list[str]) -> list[dict]:
        return retrieve_explanation_claims(query, restaurant_ids, claim_types)


def configured_explanation_service() -> RecommendationExplanationService:
    llm_enabled = os.getenv("AI_LLM_EXPLANATION_ENABLED", "false").strip().lower() == "true"
    client = None
    if llm_enabled:
        timeout = float(os.getenv("RECOMMENDATION_EXPLANATION_TIMEOUT_SECONDS", "24"))
        if not 1 <= timeout <= 60:
            raise ValueError("recommendation explanation timeout must be within 1..60 seconds")
        model = os.getenv("RECOMMENDATION_EXPLANATION_MODEL") or configured_qwen_model()
        client = OllamaClient(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=model,
            timeout=timeout,
            num_predict=256,
        )
    return RecommendationExplanationService(client, FinalCandidateEvidenceRetriever(), llm_enabled)
