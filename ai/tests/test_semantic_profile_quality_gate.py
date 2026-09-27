import pytest

from app.semantic_profile_quality_gate import (
    AssertionVerdict,
    AtomicAssertion,
    ClaimCandidate,
    SemanticVerdict,
    aggregate_assertion_verdicts,
    atomicizer_prompt,
    atomicizer_schema,
    normalize_claim_key,
    parse_assertion_verdict,
    parse_atomicization,
    parse_verdict,
    raw_evidence_text,
    regression_is_blocked,
    semantic_error_category,
    validate_claim,
    verdict_is_indexable,
    verifier_prompt,
)


def _claim(**overrides):
    value = {
        "restaurantId": 42,
        "claimId": "42:DINING_CONTEXT:1",
        "claimType": "DINING_CONTEXT",
        "claimText": "혼자 식사하기 좋은 곳",
        "evidenceIds": ["E001"],
        "supportQuotes": [{"evidenceId": "E001", "quote": "혼밥하기 좋아요"}],
    }
    value.update(overrides)
    return value


def _evidence(**overrides):
    value = {
        "restaurantId": 42,
        "evidenceId": "E001",
        "evidenceType": "keyword",
        "status": "SUCCESS",
        "rawText": '"혼밥하기 좋아요" 이 키워드를 선택한 인원',
    }
    value.update(overrides)
    return value


def test_exact_quote_and_restaurant_evidence_pass_deterministic_validation():
    checked = validate_claim(_claim(), {"E001": _evidence()}, expected_restaurant_id=42)
    assert checked["valid"] is True
    assert checked["quoteValid"] is True
    assert checked["evidenceIntegrityValid"] is True


@pytest.mark.parametrize(
    ("claim", "evidence", "restaurant_id", "error"),
    [
        (_claim(evidenceIds=["MISSING"], supportQuotes=[]), {}, 42, "EVIDENCE_NOT_FOUND:MISSING"),
        (_claim(), {"E001": _evidence(restaurantId=7)}, 42, "EVIDENCE_RESTAURANT_MISMATCH:E001"),
        (
            _claim(supportQuotes=[{"evidenceId": "E001", "quote": "맛있어요"}]),
            {"E001": _evidence()},
            42,
            "QUOTE_NOT_EXACT_SUBSTRING:E001",
        ),
        (_claim(), {"E001": _evidence(status="FAILED")}, 42, "EVIDENCE_NOT_SUCCESS:E001"),
    ],
)
def test_invalid_evidence_or_quote_fails_closed(claim, evidence, restaurant_id, error):
    checked = validate_claim(claim, evidence, expected_restaurant_id=restaurant_id)
    assert checked["valid"] is False
    assert error in checked["errors"]


def test_missing_quote_and_duplicate_claim_are_detected():
    checked = validate_claim(
        _claim(supportQuotes=[]),
        {"E001": _evidence()},
        expected_restaurant_id=42,
        duplicate=True,
    )
    assert "SUPPORT_QUOTE_MISSING:E001" in checked["errors"]
    assert "DUPLICATE_CLAIM" in checked["errors"]


def test_malformed_claim_schema_fails_closed():
    checked = validate_claim({"claimId": "missing fields"}, {}, expected_restaurant_id=42)
    assert checked["valid"] is False
    assert checked["claim"] is None


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [("SUPPORTED", True), ("PARTIAL", False), ("UNSUPPORTED", False)],
)
def test_verdict_indexability_requires_deterministic_pass_and_supported(verdict, expected):
    deterministic = {"valid": True, "quoteValid": True}
    semantic = SemanticVerdict(
        verdict=verdict,
        supportedPortion="direct portion",
        unsupportedPortion="",
        evidenceIds=["E001"],
    )
    assert verdict_is_indexable(deterministic, semantic) is expected
    assert verdict_is_indexable({"valid": False, "quoteValid": True}, semantic) is False


def test_verifier_error_and_known_overclaim_cannot_be_approved():
    assert verdict_is_indexable({"valid": True, "quoteValid": True}, None) is False
    assert regression_is_blocked("SUPPORTED", ["PARTIAL", "UNSUPPORTED"], True) is False
    assert regression_is_blocked("PARTIAL", ["PARTIAL", "UNSUPPORTED"], False) is True
    assert regression_is_blocked("UNSUPPORTED", ["PARTIAL", "UNSUPPORTED"], False) is True


def test_verifier_parse_rejects_invalid_json_schema_and_unknown_evidence():
    with pytest.raises(ValueError, match="INVALID_VERIFIER_OUTPUT"):
        parse_verdict("not json", {"E001"})
    payload = {
        "verdict": "SUPPORTED",
        "supportedPortion": "all",
        "unsupportedPortion": "",
        "evidenceIds": ["E999"],
    }
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE"):
        parse_verdict(payload, {"E001"})


def test_verifier_prompt_has_only_claim_and_raw_evidence_not_generator_metadata():
    prompt = verifier_prompt(
        ClaimCandidate.model_validate(_claim()),
        [
            {
                **_evidence(),
                "rawEvidence": {"keyword": "secret extra field"},
                "oldStatus": "AUTO_APPROVED",
            }
        ],
    )
    assert "혼자 식사하기 좋은 곳" in prompt
    assert "혼밥하기 좋아요" in prompt
    assert "secret extra field" in prompt
    assert "AUTO_APPROVED" not in prompt


def test_raw_evidence_text_preserves_original_keyword_text():
    source = {
        "evidenceType": "keyword",
        "content": {"keyword": '"혼밥하기 좋아요" 이 키워드를 선택한 인원'},
    }
    assert raw_evidence_text(source) == '"혼밥하기 좋아요" 이 키워드를 선택한 인원'


def test_duplicate_key_is_restaurant_claim_type_and_normalized_text():
    first = ClaimCandidate.model_validate(_claim(claimText="  혼자   식사하기 좋은 곳 "))
    second = ClaimCandidate.model_validate(
        _claim(claimId="other", claimText="혼자 식사하기 좋은 곳")
    )
    assert normalize_claim_key(first) == normalize_claim_key(second)


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        (["SUPPORTED", "SUPPORTED"], "SUPPORTED"),
        (["SUPPORTED", "UNSUPPORTED"], "PARTIAL"),
        (["UNSUPPORTED", "UNSUPPORTED"], "UNSUPPORTED"),
    ],
)
def test_python_aggregates_binary_assertion_results(verdicts, expected):
    assertions = [
        AtomicAssertion(assertionId=f"A{i}", text=f"fact {i}", sourceSpan=f"span {i}")
        for i, _ in enumerate(verdicts)
    ]
    results = [AssertionVerdict(verdict=value, evidenceIds=["E001"]) for value in verdicts]
    assert aggregate_assertion_verdicts(assertions, results) == expected


def test_aggregator_rejects_empty_or_incomplete_assertion_results():
    with pytest.raises(ValueError, match="COUNT_MISMATCH"):
        aggregate_assertion_verdicts([], [])
    with pytest.raises(ValueError, match="COUNT_MISMATCH"):
        aggregate_assertion_verdicts(
            [AtomicAssertion(assertionId="A1", text="fact", sourceSpan="fact")], []
        )


def test_atomicization_uses_model_assertion_and_python_generated_source_trace():
    parsed = parse_atomicization(
        {
            "assertions": [
                {"text": "혼자 식사에 적합하다", "startToken": 0, "endToken": 0},
                {"text": "공간이 넓다", "startToken": 1, "endToken": 1},
            ]
        },
        "혼밥하기 적합하고 매장이 넓어 편안하다",
    )
    assert len(parsed.assertions) == 2
    assert [item.assertionId for item in parsed.assertions] == ["A1", "A2"]
    assert [item.text for item in parsed.assertions] == ["혼자 식사에 적합하다", "공간이 넓다"]
    assert [item.sourceSpan for item in parsed.assertions] == ["혼밥하기", "적합하고"]
    overlapping = parse_atomicization(
        {
            "assertions": [
                {"text": "family gatherings are suitable", "startToken": 0, "endToken": 5},
                {"text": "corporate dinners are suitable", "startToken": 2, "endToken": 5},
            ]
        },
        "family and corporate dinners are suitable",
    )
    assert len(overlapping.assertions) == 2
    assert [item.sourceSpan for item in overlapping.assertions] == [
        "family and corporate dinners are suitable",
        "corporate dinners are suitable",
    ]
    reordered = parse_atomicization(
        {
            "assertions": [
                {"text": "second", "startToken": 1, "endToken": 1},
                {"text": "first", "startToken": 0, "endToken": 0},
            ]
        },
        "first second",
    )
    assert [item.assertionId for item in reordered.assertions] == ["A1", "A2"]
    assert [item.text for item in reordered.assertions] == ["first", "second"]
    with pytest.raises(ValueError, match="INVALID_TOKEN_RANGE"):
        parse_atomicization(
            {"assertions": [{"text": "bad", "startToken": 1, "endToken": 2}]}, "혼밥하기"
        )
    with pytest.raises(ValueError, match="DUPLICATE"):
        parse_atomicization(
            {
                "assertions": [
                    {"text": "same", "startToken": 0, "endToken": 0},
                    {"text": "same", "startToken": 0, "endToken": 0},
                ]
            },
            "사실",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"assertions": []},
        {"assertions": [{"text": "x", "startToken": 0, "endToken": 0}] * 9},
        "malformed",
    ],
)
def test_atomicization_malformed_empty_and_over_limit_fail_closed(payload):
    with pytest.raises(ValueError):
        parse_atomicization(payload, "x")


@pytest.mark.parametrize(
    ("payload", "claim", "error"),
    [
        ([], "x", "ROOT_SCHEMA_MISMATCH"),
        ({}, "x", "ASSERTIONS_MISSING"),
        ({"assertions": []}, "x", "ASSERTIONS_EMPTY"),
        ({"assertions": [3]}, "x", "INVALID_FIELD_TYPE"),
        (
            {"assertions": [{"text": "x", "startToken": 0, "endToken": 0, "x": 1}]},
            "x",
            "EXTRA_UNEXPECTED_STRUCTURE",
        ),
        ({"assertions": [{"startToken": 0, "endToken": 0}]}, "x", "ASSERTION_FIELD_MISSING"),
        (
            {"assertions": [{"text": "x", "startToken": "0", "endToken": 0}]},
            "x",
            "INVALID_FIELD_TYPE",
        ),
        (
            {"assertions": [{"text": "x", "startToken": 1, "endToken": 2}]},
            "x",
            "INVALID_TOKEN_RANGE",
        ),
        (
            {
                "assertions": [
                    {"text": "a", "startToken": 0, "endToken": 0},
                    {"text": "b", "startToken": 0, "endToken": 0},
                ]
            },
            "x",
            "DUPLICATE_ASSERTION",
        ),
    ],
)
def test_atomicizer_contract_errors_are_distinguishable(payload, claim, error):
    with pytest.raises(ValueError, match=error):
        parse_atomicization(payload, claim)


def test_atomicizer_structured_schema_bounds_indices_to_this_claim():
    schema = atomicizer_schema(3)
    span_schema = schema["properties"]["assertions"]["items"]["properties"]
    assert span_schema["startToken"]["enum"] == [0, 1, 2]
    assert span_schema["endToken"]["enum"] == [0, 1, 2]


@pytest.mark.parametrize(
    ("claim_type", "claim_text", "span"),
    [
        (
            "DINING_CONTEXT",
            "혼자 식사와 빠른 식사가 가능하다",
            {"text": "혼자 식사에 적합하다", "startToken": 0, "endToken": 1},
        ),
        (
            "TASTE",
            "Delicious, 신선한 재료",
            {"text": "재료가 신선하다", "startToken": 1, "endToken": 2},
        ),
        (
            "FOOD_MENTION",
            "고객 리뷰 keyword에서 떡볶이가 반복 언급된다",
            {"text": "떡볶이가 언급된다", "startToken": 3, "endToken": 4},
        ),
        (
            "MENU_CHARACTERISTIC",
            "The menu has pasta and set meals",
            {"text": "pasta 메뉴가 있다", "startToken": 3, "endToken": 3},
        ),
    ],
)
def test_atomicizer_contract_handles_korean_english_and_mixed_claims(claim_type, claim_text, span):
    parsed = parse_atomicization({"assertions": [span]}, claim_text)
    assert parsed.assertions[0].text == span["text"]
    assert parsed.assertions[0].sourceSpan == " ".join(
        claim_text.split()[span["startToken"] : span["endToken"] + 1]
    )
    claim = ClaimCandidate.model_validate(_claim(claimType=claim_type, claimText=claim_text))
    prompt = atomicizer_prompt(claim)
    assert "Evidence는 제공되지 않는다" in prompt
    assert "claimUnits" in prompt
    assert "쉼표로 나열된 사실은 각각 별도 범위" in prompt
    assert "sourceSpan은 Python이 원문에서 생성" in prompt
    correction_prompt = atomicizer_prompt(claim, correction=True)
    assert (
        "previous output violated the generic atomic assertion/source span contract"
        in correction_prompt
    )
    assert claim.claimId not in correction_prompt


def test_atomicizer_semantic_error_categories_preserve_validation_stage():
    assert semantic_error_category(ValueError("ATOMICIZER_INVALID_JSON")) == "INVALID_JSON"
    assert (
        semantic_error_category(ValueError("ATOMICIZER_INVALID_TOKEN_RANGE:location=spans.0"))
        == "INVALID_TOKEN_RANGE"
    )
    assert (
        semantic_error_category(ValueError("ATOMICIZER_ASSERTIONS_MISSING:location=fragments"))
        == "ASSERTIONS_MISSING"
    )
    assert semantic_error_category(ValueError("ATOMICIZER_EMPTY_OUTPUT")) == "EMPTY_OUTPUT"


def test_assertion_verdict_is_binary_and_evidence_scoped():
    result = parse_assertion_verdict({"verdict": "UNSUPPORTED", "evidenceIds": ["E001"]}, {"E001"})
    assert result.verdict == "UNSUPPORTED"
    assert (
        parse_assertion_verdict({"verdict": "UNSUPPORTED", "evidenceIds": []}, {"E001"}).evidenceIds
        == []
    )
    with pytest.raises(ValueError, match="SCHEMA_ERROR"):
        parse_assertion_verdict({"verdict": "PARTIAL", "evidenceIds": ["E001"]}, {"E001"})
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE"):
        parse_assertion_verdict({"verdict": "SUPPORTED", "evidenceIds": ["E999"]}, {"E001"})
    with pytest.raises(ValueError, match="WITHOUT_EVIDENCE"):
        parse_assertion_verdict({"verdict": "SUPPORTED", "evidenceIds": []}, {"E001"})
