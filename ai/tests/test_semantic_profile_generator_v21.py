from __future__ import annotations

from scripts.run_semantic_profile_generator_v21 import _prompt_evidence


def test_prompt_evidence_interleaves_available_sources_without_losing_order():
    catalog = {
        "items": [
            {
                "evidenceId": "E001",
                "evidenceType": "menu",
                "status": "SUCCESS",
                "content": {"name": "메뉴1"},
            },
            {
                "evidenceId": "E002",
                "evidenceType": "menu",
                "status": "SUCCESS",
                "content": {"name": "메뉴2"},
            },
            {
                "evidenceId": "E003",
                "evidenceType": "keyword",
                "status": "SUCCESS",
                "content": {"keyword": "키워드1"},
            },
            {
                "evidenceId": "E004",
                "evidenceType": "review",
                "status": "SUCCESS",
                "content": {"text": "리뷰1"},
            },
            {
                "evidenceId": "E005",
                "evidenceType": "keyword",
                "status": "SUCCESS",
                "content": {"keyword": "키워드2"},
            },
        ]
    }

    prompt_rows, _ = _prompt_evidence(catalog, 42)

    assert [row["sourceType"] for row in prompt_rows] == [
        "menu",
        "keyword",
        "review",
        "menu",
        "keyword",
    ]
    assert [row["evidenceId"] for row in prompt_rows] == [
        "E001",
        "E003",
        "E004",
        "E002",
        "E005",
    ]
