"""Bounded Semantic Profile -> embedding -> Qdrant shadow pilot."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

EMBEDDING_MODEL = "qwen3-embedding:0.6b"
EMBEDDING_VERSION = "semantic-profile-embedding-v1"
COLLECTION = "zeropay_semantic_profile_pilot_v1"
RESTAURANT_IDS = (9617, 9731, 9567, 9580)
QUERIES = (
    "혼밥하기 좋은 음식점",
    "빠르게 먹기 좋은 음식점",
    "가성비 좋은 음식점",
    "맛있다는 평가가 많은 음식점",
    "한식 또는 한정식이 먹고 싶다",
    "피자나 파스타가 먹고 싶다",
    "스시나 일식이 먹고 싶다",
    "떡볶이와 김밥을 먹고 싶다",
)


def _request(
    base: str, path: str, method: str = "GET", body: dict[str, Any] | None = None,
    *, timeout: float = 60.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def load_documents(root: Path) -> list[dict[str, Any]]:
    documents = []
    approved = json.loads((root / "semantic_profile_v1_approved_9617.json").read_text())
    sources = {9617: approved}
    for restaurant_id in (9731, 9567, 9580):
        result = json.loads(
            (
                root
                / f"semantic_profile_pilot_{restaurant_id}/semantic_profile_v1_shadow_results.json"
            ).read_text()
        )
        sources[restaurant_id] = result["finalProfile"]
    for restaurant_id in RESTAURANT_IDS:
        profile = sources[restaurant_id]
        claims = profile.get("claims", [])
        text = " ".join(f"{claim['claimType']}: {claim['text']}" for claim in claims)
        documents.append(
            {
                "restaurantId": restaurant_id,
                "venueId": profile.get("venueId"),
                "profileVersion": profile["profileVersion"],
                "inputHash": profile["inputHash"],
                "catalogHash": profile["catalogHash"],
                "claimTypes": [claim["claimType"] for claim in claims],
                "claims": claims,
                "evidenceIds": sorted(
                    {evidence_id for claim in claims for evidence_id in claim["evidenceIds"]}
                ),
                "embeddingText": text,
                "embeddingModel": EMBEDDING_MODEL,
                "embeddingVersion": EMBEDDING_VERSION,
            }
        )
    return documents


def embed(ollama: str, text: str, *, timeout: float = 60.0) -> list[float]:
    result = _request(ollama, "/api/embed", "POST", {"model": EMBEDDING_MODEL, "input": [text]}, timeout=timeout)
    vectors = result.get("embeddings")
    if not vectors or not vectors[0]:
        raise RuntimeError("Ollama returned no embedding")
    return vectors[0]


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "AI_Answer"
    ollama = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    qdrant = os.getenv("QDRANT_URL", "http://localhost:6333")
    documents = load_documents(root)
    vectors = [embed(ollama, document["embeddingText"]) for document in documents]
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise RuntimeError("embedding dimension mismatch")
    existing = _request(qdrant, "/collections").get("result", {}).get("collections", [])
    if any(item.get("name") == COLLECTION for item in existing):
        raise RuntimeError(f"pilot collection already exists; refusing to modify: {COLLECTION}")
    _request(
        qdrant,
        f"/collections/{COLLECTION}",
        "PUT",
        {"vectors": {"size": dimension, "distance": "Cosine"}},
    )
    points = [
        {"id": document["restaurantId"], "vector": vector, "payload": document}
        for document, vector in zip(documents, vectors, strict=True)
    ]
    _request(qdrant, f"/collections/{COLLECTION}/points?wait=true", "PUT", {"points": points})
    manifest = {
        "collection": COLLECTION,
        "embeddingModel": EMBEDDING_MODEL,
        "embeddingVersion": EMBEDDING_VERSION,
        "dimension": dimension,
        "distance": "Cosine",
        "restaurantIds": list(RESTAURANT_IDS),
        "documents": [
            {key: value for key, value in document.items() if key != "claims"}
            for document in documents
        ],
    }
    (root / "semantic_embedding_qdrant_indexing_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    evaluations = []
    for query in QUERIES:
        query_vector = embed(ollama, query)
        response = _request(
            qdrant,
            f"/collections/{COLLECTION}/points/query",
            "POST",
            {"query": query_vector, "limit": 3, "with_payload": True},
        )
        results = response.get("result", {}).get("points", response.get("result", []))
        evaluations.append(
            {
                "query": query,
                "topK": [
                    {
                        "restaurantId": item.get("id"),
                        "score": item.get("score"),
                        "claimTypes": item.get("payload", {}).get("claimTypes", []),
                        "claims": item.get("payload", {}).get("claims", []),
                        "evidenceIds": item.get("payload", {}).get("evidenceIds", []),
                    }
                    for item in results
                ],
            }
        )
    (root / "semantic_embedding_qdrant_query_evaluation.json").write_text(
        json.dumps({"collection": COLLECTION, "queries": evaluations}, ensure_ascii=False, indent=2)
        + "\n"
    )
    print(
        json.dumps(
            {
                "collection": COLLECTION,
                "dimension": dimension,
                "documents": len(documents),
                "queries": len(QUERIES),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
