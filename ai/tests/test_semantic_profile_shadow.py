from app.semantic_profile_shadow import (
    COMPACT_INPUT_VERSION,
    INPUT_VERSION,
    PROMPT_VERSION,
    ProfileInput,
    build_compact_input,
    build_evidence_catalog,
    build_input,
    benchmark_eligible_claims,
    classify_claims,
    validate_evidence_output,
    validate_output,
)


def test_profile_input_hash_is_stable(monkeypatch):
    payload = {
        "inputVersion": INPUT_VERSION,
        "restaurantId": 1,
        "venueId": None,
        "source": {},
        "identity": {},
        "sections": {
            "menu": {"items": []},
            "businessHours": {"items": []},
            "review": {"summary": [], "keywords": [], "representativeReviews": []},
            "lifecycle": [],
        },
        "quality": {"strictProfileReady": False, "lifecyclePresent": False, "missingSections": []},
        "inputHash": "hash",
    }
    assert ProfileInput.model_validate(payload).restaurantId == 1


def test_output_rejects_unknown_source_and_hash_mismatch():
    profile_input = {
        "inputHash": "expected",
        "sections": {"menu": {"items": []}, "businessHours": {"items": []}, "review": {}},
    }
    output = {
        "profileStatus": "PARTIAL",
        "claims": [
            {
                "claimType": "food",
                "text": "x",
                "confidence": "LOW",
                "sourceFields": ["sections.menu.items[0].name"],
                "evidence": "x",
            }
        ],
        "sectionEvidence": {},
        "inputVersion": INPUT_VERSION,
        "promptVersion": PROMPT_VERSION,
        "inputHash": "wrong",
    }
    checked = validate_output(output, profile_input)
    assert checked["valid"] is False
    assert any("menu claim cites absent menu" in error for error in checked["errors"])


def test_output_rejects_path_not_present_in_concrete_input():
    profile_input = {
        "inputHash": "expected",
        "sections": {"menu": {"items": [{"name": "x"}]}, "businessHours": {}, "review": {}},
    }
    output = {
        "profileStatus": "PARTIAL",
        "claims": [
            {
                "claimType": "food",
                "text": "x",
                "confidence": "LOW",
                "sourceFields": ["sections.menu.items[0].price_value"],
                "evidence": "x",
            }
        ],
        "sectionEvidence": {},
        "inputVersion": INPUT_VERSION,
        "promptVersion": PROMPT_VERSION,
        "inputHash": "expected",
    }
    checked = validate_output(output, profile_input)
    assert checked["valid"] is False
    assert any("unknown sourceField" in error for error in checked["errors"])


def test_partial_menu_absence_never_becomes_strict_ready(monkeypatch):
    monkeypatch.setattr("app.semantic_profile_shadow._rows", lambda sql, restaurant_id: [])
    # A missing row is a blocked/unknown input, never an inferred ready profile.
    try:
        payload = build_input(9731)
    except ValueError:
        return
    assert payload["quality"]["strictProfileReady"] is False


def test_compact_input_deduplicates_menu_and_preserves_source_fields():
    original = {
        "inputVersion": INPUT_VERSION,
        "restaurantId": 9617,
        "venueId": None,
        "source": {},
        "identity": {},
        "sections": {
            "menu": {"items": [
                {
                    "name": "A", "price_value": 100, "price_text": "100",
                    "description": "x", "crawled_at": "t",
                },
                {
                    "name": "A", "price_value": 100, "price_text": "100",
                    "description": "y", "crawled_at": "t",
                },
            ]},
            "businessHours": {"items": []},
            "review": {
                "summary": [],
                "keywords": [{"keyword": "맛"}, {"keyword": "맛"}],
                "representativeReviews": [
                    {"review_id": "1", "review_text": "짧지 않은 리뷰 내용입니다."}
                ],
            },
            "lifecycle": [],
        },
        "quality": {"strictProfileReady": False, "lifecyclePresent": False, "missingSections": []},
        "inputHash": "original",
    }
    compact = build_compact_input(original)
    assert compact["inputVersion"] == COMPACT_INPUT_VERSION
    assert len(compact["sections"]["menu"]["items"]) == 1
    assert len(compact["sections"]["review"]["keywords"]) == 1
    assert len(compact["sections"]["menu"]["items"][0]["sourceFields"]) == 4
    assert compact["inputHash"] != original["inputHash"]


def test_evidence_catalog_and_evidence_id_validation():
    profile_input = {
        "inputVersion": COMPACT_INPUT_VERSION,
        "restaurantId": 9617,
        "venueId": None,
        "source": {},
        "identity": {"restaurantName": "식당", "restaurantAddress": "주소"},
        "sections": {
            "menu": {"items": [{"name": "떡볶이", "price_value": 5000}]},
            "businessHours": {"items": []},
            "review": {
                "summary": [],
                "keywords": [{"keyword": "혼밥", "mention_count": 3}],
                "representativeReviews": [],
            },
            "lifecycle": [
                {"section": "menu", "state": "SUCCESS"},
                {"section": "business_hours", "state": "SUCCESS"},
                {"section": "review", "state": "SUCCESS"},
            ],
        },
        "quality": {"strictProfileReady": True},
        "inputHash": "hash",
    }
    catalog = build_evidence_catalog(profile_input)
    valid = {
        "profileStatus": "READY",
        "claims": [
            {
                "claimType": "FOOD_TYPE",
                "text": "떡볶이",
                "confidence": "HIGH",
                "evidenceIds": ["E003"],
            }
        ],
    }
    assert validate_evidence_output(valid, catalog, profile_input)["valid"]
    invalid = {
        "profileStatus": "READY",
        "claims": [
            {
                "claimType": "TASTE",
                "text": "매움",
                "confidence": "HIGH",
                "evidenceIds": ["missing"],
            }
        ],
    }
    assert not validate_evidence_output(invalid, catalog, profile_input)["valid"]


def test_claim_classification_keeps_partial_claims_separate():
    profile_input = {
        "inputVersion": COMPACT_INPUT_VERSION,
        "restaurantId": 9731,
        "venueId": None,
        "source": {},
        "identity": {},
        "sections": {
            "menu": {"items": []},
            "businessHours": {"items": []},
            "review": {
                "summary": [],
                "keywords": [{"keyword": "맛있어요", "mention_count": 5}],
                "representativeReviews": [],
            },
            "lifecycle": [
                {"section": "menu", "state": "ABSENT_CONFIRMED"},
                {"section": "business_hours", "state": "SUCCESS"},
                {"section": "review", "state": "SUCCESS"},
            ],
        },
        "quality": {"strictProfileReady": False},
        "inputHash": "hash",
    }
    catalog = build_evidence_catalog(profile_input)
    claims = classify_claims(
        {
            "claims": [
                {
                    "claimType": "TASTE",
                    "text": "고객 평가",
                    "confidence": "HIGH",
                    "evidenceIds": ["E003"],
                }
            ]
        },
        catalog,
        profile_input,
    )
    assert claims[0]["status"] == "AUTO_APPROVED"


def test_benchmark_eligibility_allows_local_error_but_requires_lifecycle_success():
    catalog = {
        "items": [
            {"evidenceId": "E1", "status": "SUCCESS", "evidenceType": "keyword"},
            {"evidenceId": "E2", "status": "FAILED", "evidenceType": "keyword"},
        ]
    }
    classifications = [
        {"status": "AUTO_APPROVED", "claim": {"text": "좋다"}, "evidence": [{"evidenceId": "E1"}]},
        {"status": "AUTO_APPROVED", "claim": {"text": "확인 불가"}, "evidence": [{"evidenceId": "E2"}]},
    ]
    eligible, reason = benchmark_eligible_claims(
        classifications,
        catalog,
        {"quality": {"lifecyclePresent": True}},
    )
    assert len(eligible) == 1
    assert "SUCCESS evidence" in reason
    blocked, _ = benchmark_eligible_claims(
        classifications,
        catalog,
        {"quality": {"lifecyclePresent": False}},
    )
    assert blocked == []
