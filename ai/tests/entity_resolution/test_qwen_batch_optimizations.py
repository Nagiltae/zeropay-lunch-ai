"""Qwen HTTP 연결 재사용과 candidate payload 최적화를 fake client로 검증한다."""

import http.client
import json

from app.entity_resolution.qwen_candidate_matcher import (
    OllamaClient,
    QwenCandidateMatcher,
    parse_qwen_semantic_decision,
)
from app.naver.place_resolver import PlaceCandidate, RestaurantReference


def _reference():
    return RestaurantReference(
        1, "테스트 식당", "서울 강남구 논현동 1", 37.5, 127.0, "논현동", "m1",
    )


def test_ollama_client_reuses_http_connection(monkeypatch):
    created = []
    payloads = []

    class FakeResponse:
        status = 200

        def read(self):
            return b'{"response":"{\\"candidateIndices\\":[0],\\"confidence\\":\\"HIGH\\"}"}'

    class FakeConnection:
        def __init__(self, host, port=None, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.closed = False
            created.append(self)

        def request(self, method, path, body, headers):
            assert method == "POST"
            assert path == "/api/generate"
            assert "Content-Type" in headers
            payloads.append(json.loads(body))

        def getresponse(self):
            return FakeResponse()

        def close(self):
            self.closed = True

    monkeypatch.setattr(http.client, "HTTPConnection", FakeConnection)
    client = OllamaClient(base_url="http://ollama.test", model="qwen3.5:9b")
    client.complete("system", "prompt", {})
    client.complete("system", "prompt", {})
    assert len(created) == 1
    client.close()
    assert created[0].closed
    assert payloads[0]["options"]["num_predict"] == 1024


def test_qwen_matcher_reports_each_actual_attempt():
    calls = []

    class FakeClient:
        def complete(self, system, user, response_schema):
            return '{"candidateIndices":[0],"confidence":"HIGH"}'

    matcher = QwenCandidateMatcher(
        FakeClient(), on_call=lambda operation, latency: calls.append((operation, latency)),
    )
    candidate = PlaceCandidate("테스트 식당", "서울 강남구 논현동 1", "한식", "", "1")
    matcher.choose(_reference(), [candidate])
    assert len(calls) == 1
    assert calls[0][0] == "choose"
    assert calls[0][1] >= 0


def test_single_candidate_can_validate_without_choose():
    calls = []

    class FakeClient:
        def complete(self, system, user, response_schema):
            calls.append(response_schema)
            return '{"entity_match":"MATCH","business_type":"FOOD",' \
                   '"location_scope":"IN_SCOPE","final_decision":"ACCEPT",' \
                   '"reason":"same address"}'

    matcher = QwenCandidateMatcher(FakeClient())
    result = matcher.validate(
        _reference(),
        PlaceCandidate("테스트 식당", "서울 강남구 논현동 1", "한식", "", "1"),
    )
    assert result.final_decision == "ACCEPT"
    assert len(calls) == 1


def test_validate_many_returns_candidates_in_index_order():
    class FakeClient:
        def complete(self, system, user, response_schema):
            return '{"results":[' \
                   '{"candidateIndex":1,"entity_match":"NO_MATCH","business_type":"FOOD",' \
                   '"location_scope":"OUT_OF_SCOPE","final_decision":"REJECT","reason":"branch"},' \
                   '{"candidateIndex":0,"entity_match":"MATCH","business_type":"FOOD",' \
                   '"location_scope":"IN_SCOPE","final_decision":"ACCEPT","reason":"same"}]}'

    matcher = QwenCandidateMatcher(FakeClient())
    candidates = (
        PlaceCandidate("첫째", "서울 강남구 논현동 1", "한식", "", "1"),
        PlaceCandidate("둘째", "서울 강남구 논현동 2", "한식", "", "2"),
    )
    decisions = matcher.validate_many(_reference(), candidates)
    assert [decision.final_decision for decision in decisions] == ["ACCEPT", "REJECT"]


def test_semantic_contract_contradiction_is_invalid_not_overridden():
    import pytest

    with pytest.raises(ValueError, match="contradictory"):
        parse_qwen_semantic_decision(
            '{"entity_match":"NO_MATCH","business_type":"FOOD",'
            '"location_scope":"IN_SCOPE","final_decision":"ACCEPT","reason":"conflict"}'
        )
