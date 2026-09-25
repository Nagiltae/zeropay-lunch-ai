"""Opt-in read-only test of the existing v12 points; never creates a collection."""

import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.semantic_embedding_qdrant_pilot import _request


@pytest.mark.skipif(
    os.getenv("SEMANTIC_RUNTIME_LIVE") != "1", reason="requires existing local v12/Ollama"
)
def test_v12_real_scope_and_no_point_mutation(monkeypatch):
    monkeypatch.setenv("QDRANT_SEMANTIC_COLLECTION", "zeropay_semantic_claim_pilot_v12")
    base = os.getenv("QDRANT_URL", "http://localhost:6333")
    path = "/collections/zeropay_semantic_claim_pilot_v12/points/scroll"

    def digest():
        data = _request(
            base, path, "POST", {"limit": 100, "with_payload": True, "with_vector": True}
        )["result"]
        assert data["next_page_offset"] is None
        points = data["points"]
        return len(points), hashlib.sha256(json.dumps(points, sort_keys=True).encode()).hexdigest()

    before = digest()
    client = TestClient(app)
    for query, scope in [("떡볶이", [9617]), ("스시", [9731]), ("스시", [9617])]:
        result = client.post(
            "/internal/v1/semantic-retrieval",
            json={"query": query, "candidateRestaurantIds": scope, "topK": 10},
        )
        assert result.status_code == 200, result.text
        assert result.json()["candidates"]
        assert {c["restaurantId"] for c in result.json()["candidates"]} <= set(scope)
    assert digest() == before
