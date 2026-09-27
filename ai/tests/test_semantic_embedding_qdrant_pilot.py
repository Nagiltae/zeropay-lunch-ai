from pathlib import Path

import pytest

from app.semantic_embedding_qdrant_pilot import load_documents


def test_legacy_profiles_without_source_scope_fail_closed_before_embedding():
    with pytest.raises(ValueError, match="CLAIM_NOT_INDEXABLE"):
        load_documents(Path(__file__).parents[2] / "AI_Answer")
