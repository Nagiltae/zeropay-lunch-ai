from __future__ import annotations

import pytest

from app.semantic_profile_generator_v2 import (
    atomicity_rejection,
    generator_prompt,
    generator_schema,
    has_provenance_leak,
    validate_generator_output,
)


@pytest.fixture
def catalog():
    return {
        "items": [
            {
                "evidenceId": "E001",
                "evidenceType": "menu",
                "sourceField": "sections.menu.items[0]",
                "status": "SUCCESS",
                "content": {"name": "마성떡볶이", "price": 6000},
            },
            {
                "evidenceId": "E002",
                "evidenceType": "keyword",
                "sourceField": "sections.review.keywords[0]",
                "status": "SUCCESS",
                "content": {
                    "keyword": '"혼밥하기 좋아요" 이 키워드를 선택한 인원',
                    "mentionCount": 10,
                },
            },
        ]
    }


def _candidate(**updates):
    claim = {
        "claimType": "FOOD_TYPE",
        "claimText": "메뉴에 마성떡볶이가 있다.",
        "evidenceIds": ["E001"],
        "supportQuotes": [{"evidenceId": "E001", "quote": "마성떡볶이"}],
    }
    claim.update(updates)
    return {"claims": [claim]}


def test_menu_claim_with_exact_quote_passes(catalog):
    result = validate_generator_output(_candidate(), restaurant_id=9559, catalog=catalog)
    checked = result["claims"][0]
    assert result["schemaValid"] is True
    assert checked["valid"] is True
    assert checked["claim"]["claimId"].startswith("9559:FOOD_TYPE:")
    assert checked["claim"]["supportQuotes"] == [{"evidenceId": "E001", "quote": "마성떡볶이"}]


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"evidenceIds": []}, "INVALID_SCHEMA"),
        (
            {"evidenceIds": ["E999"], "supportQuotes": [{"evidenceId": "E999", "quote": "x"}]},
            "UNKNOWN_EVIDENCE",
        ),
        ({"supportQuotes": []}, "INVALID_SCHEMA"),
        ({"supportQuotes": [{"evidenceId": "E001", "quote": "매운 떡볶이"}]}, "QUOTE_MISMATCH"),
        (
            {"supportQuotes": [{"evidenceId": "E002", "quote": "마성떡볶이"}]},
            "QUOTE_EVIDENCE_MISMATCH",
        ),
        ({"claimText": "메뉴에 떡볶이가 있다. 근거: E001"}, "PROVENANCE_TEXT_IN_CLAIM"),
    ],
)
def test_invalid_or_unsafe_candidate_fails_closed(catalog, updates, expected):
    result = validate_generator_output(_candidate(**updates), restaurant_id=9559, catalog=catalog)
    if not result["schemaValid"]:
        assert result["claims"] == []
        assert result["errors"][0]["code"] == expected
    else:
        assert expected in {item["code"] for item in result["claims"][0]["errors"]}
        assert result["claims"][0]["valid"] is False


def test_duplicate_claim_is_detected(catalog):
    payload = _candidate()
    payload["claims"].append(payload["claims"][0].copy())
    result = validate_generator_output(payload, restaurant_id=9559, catalog=catalog)
    assert result["claims"][0]["valid"] is True
    assert "DUPLICATE" in {item["code"] for item in result["claims"][1]["errors"]}


def test_review_mention_is_not_accepted_as_official_menu_fact(catalog):
    payload = {
        "claims": [
            {
                "claimType": "FOOD_TYPE",
                "claimText": "메뉴에 혼밥 떡볶이가 있다.",
                "evidenceIds": ["E002"],
                "supportQuotes": [{"evidenceId": "E002", "quote": "혼밥하기 좋아요"}],
            }
        ]
    }
    result = validate_generator_output(payload, restaurant_id=9559, catalog=catalog)
    assert "EVIDENCE_SOURCE_TYPE_NOT_ALLOWED" in {
        item["code"] for item in result["claims"][0]["errors"]
    }


def test_provenance_detector_and_output_schema_are_minimal():
    assert has_provenance_leak("FOOD_TYPE: 메뉴가 있다")
    assert has_provenance_leak("메뉴가 있다. 근거: E023")
    assert not has_provenance_leak("메뉴에 마성떡볶이가 있다.")
    schema = generator_schema()
    assert set(schema["properties"]) == {"claims"}
    claim_schema = schema["properties"]["claims"]["items"]
    assert set(claim_schema["properties"]) == {
        "claimType",
        "claimText",
        "evidenceIds",
        "supportQuotes",
    }
    assert "confidence" not in claim_schema["properties"]


def test_generator_prompt_preserves_source_role_and_quotes():
    prompt = generator_prompt(
        {"restaurantId": 9559, "name": "모우리"},
        [{"evidenceId": "E001", "sourceType": "menu", "rawText": "마성떡볶이"}],
    )
    assert "exact substring copied" in prompt
    assert "not official sale" in prompt


def test_korean_generator_contract_and_prompt(catalog):
    prompt = generator_prompt(
        {"restaurantId": 9559, "name": "모우리"},
        [{"evidenceId": "E001", "sourceType": "menu", "rawText": "마성떡볶이"}],
        max_claims=8,
        korean=True,
    )
    assert "자연스럽고 검색에 쓸 수 있는 한국어 문장" in prompt
    assert "source별 개수나 비율" in prompt
    assert generator_schema(max_claims=8)["properties"]["claims"]["maxItems"] == 8
    assert validate_generator_output(_candidate(), restaurant_id=9559, catalog=catalog)["claims"][
        0
    ]["valid"]
    payload = {"claims": [_candidate()["claims"][0] for _ in range(6)]}
    assert (
        validate_generator_output(payload, restaurant_id=9559, catalog=catalog)["schemaValid"]
        is True
    )


def test_english_boilerplate_with_korean_menu_name_is_rejected(catalog):
    result = validate_generator_output(
        _candidate(claimText="The restaurant offers 마성떡볶이 as a signature item."),
        restaurant_id=9559,
        catalog=catalog,
    )
    assert "CLAIM_NOT_KOREAN_DOMINANT" in {error["code"] for error in result["claims"][0]["errors"]}


def test_korean_claim_with_latin_brand_name_is_allowed(catalog):
    result = validate_generator_output(
        _candidate(claimText="메뉴에 ABC 마성떡볶이가 있다."),
        restaurant_id=9559,
        catalog=catalog,
    )
    assert result["claims"][0]["valid"] is True


def test_review_keyword_claim_can_be_korean_and_exactly_quoted(catalog):
    result = validate_generator_output(
        {
            "claims": [
                {
                    "claimType": "DINING_CONTEXT",
                    "claimText": "혼자 식사하기 좋다는 고객 평가가 있다.",
                    "evidenceIds": ["E002"],
                    "supportQuotes": [{"evidenceId": "E002", "quote": "혼밥하기 좋아요"}],
                }
            ]
        },
        restaurant_id=9559,
        catalog=catalog,
    )
    assert result["claims"][0]["valid"] is True
    assert result["claims"][0]["claim"]["supportQuotes"][0]["quote"] == "혼밥하기 좋아요"


def test_keyword_food_mention_has_source_framed_existing_claim_type(catalog):
    result = validate_generator_output(
        {
            "claims": [
                {
                    "claimType": "FOOD_MENTION",
                    "claimText": "고객 리뷰에서 혼밥 표현이 언급된다.",
                    "evidenceIds": ["E002"],
                    "supportQuotes": [{"evidenceId": "E002", "quote": "혼밥하기 좋아요"}],
                }
            ]
        },
        restaurant_id=9559,
        catalog=catalog,
    )
    assert result["claims"][0]["valid"] is True


@pytest.mark.parametrize("claim_type", ["FOOD_TYPE", "MENU_CHARACTERISTIC"])
def test_keyword_cannot_be_promoted_to_official_menu_claim(catalog, claim_type):
    result = validate_generator_output(
        {
            "claims": [
                {
                    "claimType": claim_type,
                    "claimText": "메뉴에 혼밥 표현이 있다.",
                    "evidenceIds": ["E002"],
                    "supportQuotes": [{"evidenceId": "E002", "quote": "혼밥하기 좋아요"}],
                }
            ]
        },
        restaurant_id=9559,
        catalog=catalog,
    )
    assert "EVIDENCE_SOURCE_TYPE_NOT_ALLOWED" in {
        error["code"] for error in result["claims"][0]["errors"]
    }


def test_source_contract_prompt_explains_existing_food_mention_and_identity_boundary():
    prompt = generator_prompt(
        {},
        [{"evidenceId": "E001", "sourceType": "keyword", "rawText": "꼼장어"}],
        max_claims=1,
        korean=True,
        source_contract_v22=True,
    )
    assert "FOOD_MENTION" in prompt
    assert "음식 이름만 단독으로 나오면 FOOD_MENTION" in prompt
    assert "VENUE_CHARACTERISTIC을 선택하세요" in prompt
    assert "서로 떨어진 구절을 연결하거나 순서를 바꾸지 마세요" in prompt
    assert "판매한다고 말하지 마세요" in prompt
    assert "평가의 의미를 TASTE로 표현하세요" in prompt
    assert "두 사실을 연결하지 마세요" in prompt
    assert "Claim 문장에 식당 이름을 넣지 마세요" in prompt
    assert "restaurantId metadata" in prompt


def test_review_keyword_food_mention_is_not_official_sale_by_type_contract():
    schema = generator_schema(max_claims=1)
    claim_types = schema["properties"]["claims"]["items"]["properties"]["claimType"]["enum"]
    assert "FOOD_MENTION" in claim_types


def test_atomicity_gate_accepts_one_assertion_and_rejects_compound_claim():
    assert atomicity_rejection(1) is None
    assert atomicity_rejection(2) == "GENERATOR_NON_ATOMIC"
    assert atomicity_rejection(0) == "GENERATOR_NON_ATOMIC"
