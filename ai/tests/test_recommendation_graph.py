from __future__ import annotations

import asyncio

import pytest

from app.semantic_runtime import (
    Candidate,
    DependencyUnavailable,
    MatchedClaim,
    RetrievalRequest,
    RetrievalResponse,
    RetryableDependencyUnavailable,
)
from app.workflows.recommendation_graph import build_recommendation_graph


def initial_state(query="떡볶이 먹고 싶어", candidate_ids=(9617, 9731)):
    return {
        "originalQuery": query,
        "candidateRestaurantIds": candidate_ids,
        "topK": 10,
        "intent": None,
        "semanticEligible": False,
        "semanticQuery": None,
        "semanticResults": None,
        "retrievalStatus": "NOT_STARTED",
        "retryCount": 0,
        "maxRetries": 1,
        "fallbackReason": None,
        "errors": [],
        "workflowRoute": "",
        "trace": [],
    }


def success_response(restaurant_id=9617):
    claim = MatchedClaim(
        claimId="c1",
        claimType="FOOD_TYPE",
        claimText="메뉴에 떡볶이가 있다.",
        semanticSimilarity=0.8,
        matchType="EXACT",
        exactMatch=True,
        synonymMatch=False,
        categoryMatch=False,
        traitMatch=False,
        mentionCount=None,
        evidenceIds=["E1"],
    )
    return RetrievalResponse(
        candidates=[Candidate(
            restaurantId=restaurant_id,
            retrievalScore=101.0,
            semanticSimilarity=0.8,
            matchedClaims=[claim],
        )]
    )


def run(graph, state):
    return asyncio.run(graph.ainvoke(state))


def test_unknown_intent_skips_retrieval():
    class NeverCalled:
        def retrieve(self, request, **kwargs):
            pytest.fail("semantic retrieval should be skipped")

    result = run(build_recommendation_graph(NeverCalled()), initial_state("점심 추천해줘"))
    assert result["workflowRoute"] == "SEMANTIC_SKIPPED"
    assert result["semanticResults"].candidates == []
    assert "semantic_retrieval" not in [entry["node"] for entry in result["trace"]]
    assert result["fallbackReason"] == "UNKNOWN_INTENT"


def test_semantic_success_preserves_candidate_scope_and_response():
    requests = []

    class Success:
        def retrieve(self, request: RetrievalRequest, **kwargs):
            requests.append(request)
            return success_response()

    original_ids = (9617, 9731)
    result = run(build_recommendation_graph(Success()), initial_state(candidate_ids=original_ids))
    assert result["workflowRoute"] == "SEMANTIC_SUCCESS"
    assert requests == [RetrievalRequest(
        query="떡볶이 먹고 싶어", candidateRestaurantIds=[9617, 9731], topK=10
    )]
    assert result["candidateRestaurantIds"] == original_ids
    assert result["response"].model_dump() == success_response().model_dump()


def test_empty_result_falls_back_without_retry():
    class Empty:
        calls = 0

        def retrieve(self, request, **kwargs):
            self.calls += 1
            return RetrievalResponse(candidates=[])

    service = Empty()
    result = run(build_recommendation_graph(service), initial_state())
    assert service.calls == 1
    assert result["retryCount"] == 0
    assert result["workflowRoute"] == "SEMANTIC_EMPTY_FALLBACK"
    assert result["fallbackReason"] == "EMPTY_RESULT"


def test_retryable_failure_then_success_retries_once_with_same_input():
    requests = []

    class RetryThenSuccess:
        def retrieve(self, request, **kwargs):
            requests.append(request)
            if len(requests) == 1:
                raise RetryableDependencyUnavailable("sanitized")
            return success_response()

    state = initial_state()
    result = run(build_recommendation_graph(RetryThenSuccess()), state)
    assert result["workflowRoute"] == "SEMANTIC_RETRY_SUCCESS"
    assert result["retryCount"] == 1
    assert result["errors"] == ["TRANSIENT_DEPENDENCY_FAILURE"]
    assert len(requests) == 2 and requests[0] == requests[1]
    assert result["candidateRestaurantIds"] == state["candidateRestaurantIds"]
    assert result["semanticQuery"] == state["originalQuery"]


def test_retry_exhaustion_falls_back_and_never_exceeds_max():
    class AlwaysRetryable:
        calls = 0

        def retrieve(self, request, **kwargs):
            self.calls += 1
            raise RetryableDependencyUnavailable("sanitized")

    service = AlwaysRetryable()
    result = run(build_recommendation_graph(service, max_retries=1), initial_state())
    assert service.calls == 2
    assert result["retryCount"] == result["maxRetries"] == 1
    assert result["workflowRoute"] == "SEMANTIC_FAILURE_FALLBACK"
    assert result["fallbackReason"] == "TRANSIENT_DEPENDENCY_FAILURE"
    assert result["errors"] == [
        "TRANSIENT_DEPENDENCY_FAILURE",
        "TRANSIENT_DEPENDENCY_FAILURE",
    ]


def test_non_retryable_failure_falls_back_without_retry():
    class InvalidResponse:
        calls = 0

        def retrieve(self, request, **kwargs):
            self.calls += 1
            raise DependencyUnavailable("invalid payload")

    service = InvalidResponse()
    result = run(build_recommendation_graph(service), initial_state())
    assert service.calls == 1
    assert result["retryCount"] == 0
    assert result["workflowRoute"] == "SEMANTIC_FAILURE_FALLBACK"
    assert result["errors"] == ["NON_RETRYABLE_DEPENDENCY_FAILURE"]


def test_candidate_ids_are_not_changed_on_retry():
    observed = []

    class RetryThenEmpty:
        def retrieve(self, request, **kwargs):
            observed.append(tuple(request.candidateRestaurantIds))
            if len(observed) == 1:
                raise RetryableDependencyUnavailable("temporary")
            return RetrievalResponse(candidates=[])

    original = (9617, 9731, 9580)
    result = run(
        build_recommendation_graph(RetryThenEmpty()),
        initial_state(candidate_ids=original),
    )
    assert observed == [original, original]
    assert result["candidateRestaurantIds"] == original


def test_http_contract_does_not_expose_workflow_state():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).post(
        "/internal/v1/semantic-retrieval",
        json={"query": "점심 추천해줘", "candidateRestaurantIds": [9617]},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"candidates", "policyVersion"}
