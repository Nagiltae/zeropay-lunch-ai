import http.client

from app.place_resolver import PlaceCandidate, RestaurantReference
from app.qwen_candidate_matcher import OllamaClient, QwenCandidateMatcher


def _reference():
    return RestaurantReference(
        1, "테스트 식당", "서울 강남구 논현동 1", 37.5, 127.0, "논현동", "m1",
    )


def test_ollama_client_reuses_http_connection(monkeypatch):
    created = []

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
