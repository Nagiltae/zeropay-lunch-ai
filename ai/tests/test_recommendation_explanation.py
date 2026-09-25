import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.recommendation_explanation import (
    ExplanationRequest,
    RecommendationExplanationService,
    configured_explanation_service,
)


class CompletionFixture:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def complete(self, system, user, response_schema):
        self.calls += 1
        assert "Safe Facts" in system
        assert "추가/삭제/재정렬하지 마라" in system
        payload = json.loads(user)
        assert "restaurants" in payload
        assert "zeroPayAvailable" not in user
        assert "budgetMatched" not in user
        assert "name" not in user
        assert "matchedClaims" not in user
        assert "facts" in payload["restaurants"][0]
        assert response_schema["properties"]["explanations"]["maxItems"] == 3
        return self.output


def request(claims=None, query="혼밥하면서 떡볶이 먹고 싶어", use_llm=True):
    return ExplanationRequest.model_validate({
        "query": query,
        "useLlm": use_llm,
        "restaurants": [{
            "restaurantId": 9617,
            "name": "마성떡볶이 논현역점",
            "matchedClaims": claims if claims is not None else [{
                "claimType": "FOOD_TYPE",
                "text": "메뉴에서 떡볶이가 확인된다.",
                "matchType": "EXACT",
                "evidenceIds": ["E011"],
            }],
            "deterministicFacts": {"zeroPayAvailable": True, "budgetMatched": True},
        }],
    })


def test_grounded_structured_explanation_is_returned_with_evidence_ids():
    client = CompletionFixture(json.dumps({"explanations": [{
        "restaurantId": 9617,
        "explanation": "떡볶이 메뉴가 확인돼 요청하신 음식과 잘 맞아요.",
        "usedEvidenceIds": ["E011"],
    }]}, ensure_ascii=False))

    response = RecommendationExplanationService(client, llm_enabled=True).explain(request())

    assert response.explanations[0].source == "LLM"
    assert response.explanations[0].restaurantId == 9617
    assert response.explanations[0].usedEvidenceIds == ["E011"]
    assert response.explanations[0].availableEvidenceIds == ["E011"]
    assert client.calls == 1


@pytest.mark.parametrize("output", [
    '{"explanations":[{"restaurantId":999,"explanation":"다른 식당이에요.","usedEvidenceIds":["E011"]}]}',
    '{"explanations":[{"restaurantId":9617,"explanation":"근처라서 좋아요.","usedEvidenceIds":["E011"]}]}',
    '{"explanations":[{"restaurantId":9617,"explanation":"무료 결제가 가능해요.","usedEvidenceIds":["E011"]}]}',
    '{"explanations":[{"restaurantId":9617,"explanation":"무비자 결제가 가능해요.","usedEvidenceIds":["E011"]}]}',
    "not-json",
])
def test_invalid_identity_unsupported_claim_or_json_uses_deterministic_fallback(output):
    response = RecommendationExplanationService(CompletionFixture(output), llm_enabled=True).explain(request())
    assert response.explanations[0].restaurantId == 9617
    assert response.explanations[0].source == "DETERMINISTIC_FALLBACK"
    assert response.explanations[0].usedEvidenceIds == ["E011"]


def test_empty_evidence_uses_fallback_without_calling_model():
    client = CompletionFixture("should not be called")
    response = RecommendationExplanationService(client).explain(request(claims=[]))
    assert response.explanations[0].source == "DETERMINISTIC_FALLBACK"
    assert response.explanations[0].usedEvidenceIds == []
    assert client.calls == 0


def test_safe_fact_conversion_limits_llm_input_to_query_relevant_claims():
    client = CompletionFixture(json.dumps({"explanations": [{
        "restaurantId": 9617,
        "explanation": "떡볶이 메뉴가 확인되어 요청하신 음식과 잘 맞아요.",
        "usedEvidenceIds": ["E011"],
    }]}, ensure_ascii=False))
    response = RecommendationExplanationService(client, llm_enabled=True).explain(request())
    assert response.explanations[0].source == "LLM"


def test_taste_safe_fact_is_limited_to_explicit_review_claim():
    client = CompletionFixture(json.dumps({"explanations": [{
        "restaurantId": 9617,
        "explanation": "가성비가 좋다는 고객 평가가 확인돼 요청하신 취향과 맞아요.",
        "usedEvidenceIds": ["E027"],
    }]}, ensure_ascii=False))
    taste_claim = [{
        "claimType": "TASTE",
        "text": "가성비가 좋다는 고객 평가가 반복된다.",
        "matchType": "TRAIT",
        "evidenceIds": ["E027"],
    }]
    result = RecommendationExplanationService(client, llm_enabled=True).explain(
        request(taste_claim, "가성비 좋은 곳"))
    assert result.explanations[0].source == "LLM"


def test_mult_intent_explanation_supplements_only_final_candidate_context_evidence():
    dining_claim = {
        "restaurantId": 9617,
        "claimType": "DINING_CONTEXT",
        "text": "혼밥하기 좋다는 고객 평가가 확인된다.",
        "matchType": "TRAIT",
        "evidenceIds": ["E023"],
    }

    class ScopedEvidence:
        def __init__(self):
            self.args = None

        def retrieve(self, query, restaurant_ids, claim_types):
            self.args = (query, restaurant_ids, claim_types)
            return [dining_claim]

    client = CompletionFixture(json.dumps({"explanations": [{
        "restaurantId": 9617,
        "explanation": "떡볶이 메뉴가 확인되고 혼밥하기 좋다는 고객 평가가 있어 요청과 잘 맞아요.",
        "usedEvidenceIds": ["E011", "E023"],
    }]}, ensure_ascii=False))
    retriever = ScopedEvidence()
    response = RecommendationExplanationService(client, retriever, llm_enabled=True).explain(request())

    assert response.explanations[0].source == "LLM"
    assert retriever.args[0] == "혼밥하면서 떡볶이 먹고 싶어"
    assert retriever.args[1] == [9617]
    assert "DINING_CONTEXT" in retriever.args[2]


def test_deterministic_fallback_combines_food_and_context_safe_facts():
    claims = [
        {"claimType": "FOOD_TYPE", "text": "떡볶이가 메뉴에 있다.", "matchType": "EXACT", "evidenceIds": ["E011"]},
        {"claimType": "DINING_CONTEXT", "text": "혼밥하기 좋다는 고객 평가가 확인된다.", "matchType": "TRAIT", "evidenceIds": ["E023"]},
    ]
    output = "not-json"
    result = RecommendationExplanationService(
        CompletionFixture(output), llm_enabled=True).explain(request(claims))
    assert result.explanations[0].source == "DETERMINISTIC_FALLBACK"
    assert result.explanations[0].explanation == (
        "떡볶이 메뉴가 확인되고 혼밥하기 좋다는 고객 평가가 확인돼 추천했어요."
    )
    assert result.explanations[0].usedEvidenceIds == ["E011", "E023"]
    assert result.explanations[0].availableEvidenceIds == ["E011", "E023"]


def test_no_secondary_intent_evidence_blocks_claim_invention_and_returns_safe_fallback():
    output = json.dumps({"explanations": [{
        "restaurantId": 9617,
        "explanation": "떡볶이 메뉴가 확인되고 혼밥하기 좋아요.",
        "usedEvidenceIds": ["E011"],
    }]}, ensure_ascii=False)
    result = RecommendationExplanationService(
        CompletionFixture(output), llm_enabled=True).explain(request())
    assert result.explanations[0].source == "DETERMINISTIC_FALLBACK"
    assert "혼밥" not in result.explanations[0].explanation


@pytest.mark.parametrize("text", [
    "무상 결제가 가능합니다.",
    "가까운 식당이에요.",
    "인기 있는 맛집이에요.",
    "평점이 좋아요.",
    "가성비가 좋아요.",
])
def test_unsupported_operational_or_unproven_semantic_terms_fallback(text):
    output = json.dumps({"explanations": [{
        "restaurantId": 9617,
        "explanation": text,
        "usedEvidenceIds": ["E011"],
    }]}, ensure_ascii=False)
    result = RecommendationExplanationService(
        CompletionFixture(output), llm_enabled=True).explain(request())
    assert result.explanations[0].source == "DETERMINISTIC_FALLBACK"


def test_timeout_uses_deterministic_fallback():
    class Timeout:
        def complete(self, *args, **kwargs):
            raise TimeoutError("private timeout details")

    response = RecommendationExplanationService(Timeout(), llm_enabled=True).explain(request())
    assert response.explanations[0].source == "DETERMINISTIC_FALLBACK"
    assert "private timeout details" not in response.model_dump_json()


def test_request_rejects_more_than_three_restaurants_and_extra_fields():
    body = request().model_dump(mode="json")
    body["restaurants"] = body["restaurants"] * 4
    response = TestClient(app).post("/internal/v1/recommendation-explanations", json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_endpoint_returns_structured_model_response(monkeypatch):
    service = RecommendationExplanationService(CompletionFixture(json.dumps({"explanations": [{
        "restaurantId": 9617,
        "explanation": "떡볶이 메뉴가 확인돼요.",
        "usedEvidenceIds": ["E011"],
    }]}, ensure_ascii=False)), llm_enabled=True)
    app.dependency_overrides[main.recommendation_explanation_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/internal/v1/recommendation-explanations", json=request().model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json()["explanations"][0]["source"] == "LLM"
    finally:
        app.dependency_overrides.pop(main.recommendation_explanation_service, None)


def test_llm_disabled_returns_safe_facts_without_completion_call():
    client = CompletionFixture("must not be called")
    response = RecommendationExplanationService(client, llm_enabled=False).explain(request(use_llm=True))
    item = response.explanations[0]
    assert client.calls == 0
    assert item.source == "DETERMINISTIC_FALLBACK"
    assert item.explanation == "떡볶이 메뉴가 확인되어 추천했어요."


def test_request_opt_out_prevents_llm_even_when_server_allows_it():
    client = CompletionFixture("must not be called")
    response = RecommendationExplanationService(client, llm_enabled=True).explain(request(use_llm=False))
    assert response.explanations[0].source == "DETERMINISTIC_FALLBACK"
    assert client.calls == 0


def test_default_configuration_does_not_construct_ollama_client(monkeypatch):
    import app.recommendation_explanation as explanation_module

    monkeypatch.setenv("AI_LLM_EXPLANATION_ENABLED", "false")
    monkeypatch.setattr(
        explanation_module, "OllamaClient",
        lambda **kwargs: pytest.fail("Ollama client must not be constructed when explanation is off"),
    )
    service = configured_explanation_service()
    assert service.client is None
    assert service.llm_enabled is False
