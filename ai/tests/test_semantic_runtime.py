import pytest
from fastapi.testclient import TestClient

from app import semantic_runtime as runtime
from app.hybrid_policy import _aggregate
from app.main import app


def point(rid=9617, text="메뉴 떡볶이", kind="FOOD_TYPE", score=0.5):
    return {
        "score": score,
        "payload": {
            "restaurantId": rid,
            "claimId": f"{rid}:claim",
            "claimType": kind,
            "normalizedClaimText": text,
            "evidenceIds": ["E011"],
        },
    }


@pytest.fixture
def dependencies(monkeypatch):
    monkeypatch.setenv("QDRANT_SEMANTIC_COLLECTION", "test-shadow")
    monkeypatch.setattr(runtime, "embed", lambda *a, **kw: [0.1] * 1024)


def test_intent_contract_and_budget():
    data = (
        TestClient(app)
        .post(
            "/internal/v1/intent-analysis",
            json={"query": "오늘 혼밥인데 12000원 안에서 떡볶이 먹고 싶어"},
        )
        .json()
    )
    assert data["maxBudget"] == 12000
    assert data["foodTerms"] == ["떡볶이"]
    assert data["diningContexts"] == ["SOLO_DINING"]
    assert runtime.analyze("1.2만원").maxBudget == 12000
    assert runtime.analyze("맛있다는 평가가 많은 곳").quantitativeTaste


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"query": " "},
        {"query": "a", "candidateRestaurantIds": [True]},
        {"query": "a", "candidateRestaurantIds": [-1]},
        {"query": "a", "candidateRestaurantIds": ["1"]},
        {"query": "a", "candidateRestaurantIds": [], "topK": 0},
    ],
)
def test_invalid_request_is_400(body):
    r = TestClient(app).post("/internal/v1/semantic-retrieval", json=body)
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_REQUEST"


def test_empty_scope_makes_no_dependency_call(monkeypatch):
    monkeypatch.setattr(runtime, "embed", lambda *a, **kw: pytest.fail("empty scope embedded"))
    r = TestClient(app).post(
        "/internal/v1/semantic-retrieval", json={"query": "a", "candidateRestaurantIds": []}
    )
    assert r.status_code == 200 and r.json()["candidates"] == []


def test_scope_is_in_qdrant_request_and_response_preserves_evidence(dependencies, monkeypatch):
    def query(base, path, method, body, **kwargs):
        assert body["filter"]["must"][0] == {"key": "restaurantId", "match": {"any": [9617]}}
        assert "DINING_CONTEXT" not in body["filter"]["must"][1]["match"]["any"]
        assert kwargs["timeout"] == 3.0
        return {"result": {"points": [point()]}}

    monkeypatch.setattr(runtime, "_request", query)
    r = TestClient(app).post(
        "/internal/v1/semantic-retrieval",
        json={"query": "떡볶이", "candidateRestaurantIds": [9617, 9617]},
    )
    c = r.json()["candidates"][0]
    assert c["restaurantId"] == 9617 and c["semanticSimilarity"] == 0.5
    assert c["retrievalScore"] > 100
    assert c["matchedClaims"][0]["matchType"] == "EXACT"
    assert c["matchedClaims"][0]["evidenceIds"] == ["E011"]


def test_explanation_evidence_lookup_scopes_final_ids_and_requested_types(dependencies, monkeypatch):
    def query(base, path, method, body, **kwargs):
        assert body["filter"]["must"][0] == {"key": "restaurantId", "match": {"any": [9617]}}
        assert body["filter"]["must"][1] == {
            "key": "claimType", "match": {"any": ["DINING_CONTEXT", "FOOD_TYPE"]}
        }
        return {"result": {"points": [
            point(9617, "떡볶이 메뉴", "FOOD_TYPE"),
            {**point(9617, "혼밥하기 좋다는 평가", "DINING_CONTEXT"),
             "payload": {**point(9617, "혼밥하기 좋다는 평가", "DINING_CONTEXT")["payload"],
                         "claimId": "9617:dining"}},
        ]}}

    monkeypatch.setattr(runtime, "_request", query)
    claims = runtime.retrieve_explanation_claims(
        "혼밥하면서 떡볶이 먹고 싶어", [9617], ["FOOD_TYPE", "DINING_CONTEXT"]
    )
    assert {claim["claimType"] for claim in claims} == {"FOOD_TYPE", "DINING_CONTEXT"}
    assert {claim["restaurantId"] for claim in claims} == {9617}


def test_explanation_evidence_lookup_rejects_out_of_scope_payload(dependencies, monkeypatch):
    monkeypatch.setattr(runtime, "_request", lambda *a, **kw: {
        "result": {"points": [point(9731, "혼밥", "DINING_CONTEXT")]}
    })
    with pytest.raises(runtime.DependencyUnavailable):
        runtime.retrieve_explanation_claims("혼밥하면서 떡볶이", [9617], ["DINING_CONTEXT"])


@pytest.mark.parametrize(
    "query,relation", [("초밥", "EXACT"), ("스시", "SYNONYM"), ("일식", "CATEGORY")]
)
def test_taxonomy_contract(dependencies, monkeypatch, query, relation):
    monkeypatch.setattr(
        runtime,
        "_request",
        lambda *a, **kw: {"result": {"points": [point(9731, "초밥", "FOOD_MENTION")]}},
    )
    r = TestClient(app).post(
        "/internal/v1/semantic-retrieval", json={"query": query, "candidateRestaurantIds": [9731]}
    )
    assert r.json()["candidates"][0]["matchedClaims"][0]["matchType"] == relation


def test_scope_violation_is_unavailable(dependencies, monkeypatch):
    monkeypatch.setattr(runtime, "_request", lambda *a, **kw: {"result": {"points": [point(9731)]}})
    r = TestClient(app).post(
        "/internal/v1/semantic-retrieval",
        json={"query": "떡볶이", "candidateRestaurantIds": [9617]},
    )
    assert r.status_code == 503 and "9731" not in r.text


@pytest.mark.parametrize("where", ["embed", "_request"])
def test_dependency_failure_is_sanitized(dependencies, monkeypatch, where):
    def fail(*a, **kw):
        raise OSError("sensitive internal detail")

    monkeypatch.setattr(runtime, where, fail)
    r = TestClient(app).post(
        "/internal/v1/semantic-retrieval",
        json={"query": "떡볶이", "candidateRestaurantIds": [9617]},
    )
    assert r.status_code == 503 and "sensitive" not in r.text


def test_bad_dimension(dependencies, monkeypatch):
    monkeypatch.setattr(runtime, "embed", lambda *a, **kw: [0.1])
    r = TestClient(app).post(
        "/internal/v1/semantic-retrieval",
        json={"query": "떡볶이", "candidateRestaurantIds": [9617]},
    )
    assert r.status_code == 503


def test_unexpected_error_sanitized(monkeypatch):
    monkeypatch.setattr("app.main.analyze", lambda q: 1 / 0)
    r = TestClient(app, raise_server_exceptions=False).post(
        "/internal/v1/intent-analysis", json={"query": "a"}
    )
    assert r.status_code == 500 and r.json()["code"] == "INTERNAL_ERROR"


def test_top_k_and_policy_shared():
    points = [point(rid) for rid in range(1, 8)]
    assert len(_aggregate(points, "떡볶이", True)) == 3
    assert len(_aggregate(points, "떡볶이", True, top_k=6)) == 6
    from app.semantic_retrieval_hybrid_v2 import _aggregate as offline

    assert offline is _aggregate


def test_quantitative_ignores_unrelated_large_count():
    good = point(1, "맛있어요", "TASTE")
    good["payload"]["mentionCount"] = 12
    unrelated = point(2, "친절해요", "TASTE")
    unrelated["payload"]["mentionCount"] = 100000
    assert [
        x["restaurantId"]
        for x in _aggregate([unrelated, good], "맛있다는 평가가 많은 곳", True, True)
    ] == [1]
