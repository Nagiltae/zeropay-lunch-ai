from pathlib import Path

from app.semantic_embedding_qdrant_pilot import EMBEDDING_MODEL, load_documents


def test_documents_use_only_approved_claims_and_deterministic_fields_are_not_text():
    documents = load_documents(Path(__file__).parents[2] / "AI_Answer")
    assert [document["restaurantId"] for document in documents] == [9617, 9731, 9567, 9580]
    for document in documents:
        assert document["embeddingModel"] == EMBEDDING_MODEL
        assert "REVIEW_REQUIRED" not in document["embeddingText"]
        assert "REJECTED" not in document["embeddingText"]
        assert "price_value" not in document["embeddingText"]
        assert "external_place_id" not in document["embeddingText"]


def test_payload_keeps_traceability_outside_embedding_text():
    document = load_documents(Path(__file__).parents[2] / "AI_Answer")[0]
    assert document["inputHash"]
    assert document["catalogHash"]
    assert document["evidenceIds"]
    assert document["evidenceIds"] == sorted(document["evidenceIds"])
