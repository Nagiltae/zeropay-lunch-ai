"""ACCEPT/REJECT/UNKNOWN 및 fingerprint·technical failure mapping을 검증한다."""

from app.entity_resolution.verification_quality_gate import (
    VerificationDecision,
    can_reuse_rejection,
    downstream_allowed,
    map_semantic_result,
    recommendation_eligibility,
    source_fingerprint,
    technical_unknown,
    unknown_reason_kind,
)


def test_provider_fusion_reuses_only_unchanged_reject_without_calls():
    from app.entity_resolution.provider_entity_resolution_cli import (
        SEARCH_POLICY_VERSION,
        evaluate_reference,
    )
    from app.naver.place_resolver import RestaurantReference

    class FailingProvider:
        def search(self, *args, **kwargs):
            raise AssertionError("provider must be skipped for cached rejection")

    class FailingMatcher:
        def choose(self, *args, **kwargs):
            raise AssertionError("Qwen must be skipped for cached rejection")

    reference = RestaurantReference(
        restaurant_id=1,
        komsco_name="테스트 식당",
        komsco_address="서울 강남구 논현동 1",
        komsco_latitude=37.51,
        komsco_longitude=127.02,
        legal_dong="논현동",
        external_merchant_id="merchant-1",
    )
    from app.entity_resolution.provider_entity_resolution_cli import _source
    cached = {
        "external_merchant_id": "merchant-1",
        "decision": "REJECT",
        "verification_reason": "NON_FOOD",
        "source_fingerprint": source_fingerprint(_source(reference)),
        "search_policy_version": SEARCH_POLICY_VERSION,
        "candidates_json": "[]",
    }
    row = evaluate_reference(
        reference, FailingProvider(), FailingProvider(), FailingMatcher(), cached
    )
    assert row["decision"] == "REJECT"
    assert row["provider_calls_skipped"] == "true"
    assert row["qwen_calls_skipped"] == "true"


def test_provider_fusion_maps_qwen_technical_failure_to_unknown():
    from app.entity_resolution.provider_entity_resolution_cli import evaluate_reference
    from app.naver.place_resolver import RestaurantReference
    from app.providers.place_provider import PlaceSearchCandidate, ProviderSearchResult

    class Provider:
        def search(self, query, **kwargs):
            return ProviderSearchResult(
                "KAKAO", query,
                (PlaceSearchCandidate(
                    "KAKAO", "1", "테스트 식당", "음식점", "서울 강남구 논현동 1", "",
                    None, None, "", "", "", {},
                ),),
            )

    class BrokenMatcher:
        def choose(self, *args, **kwargs):
            raise ValueError("bad structured output")

    reference = RestaurantReference(
        1, "테스트 식당", "서울 강남구 논현동 1", None, None, "논현동", "m1"
    )
    row = evaluate_reference(reference, Provider(), Provider(), BrokenMatcher())
    assert row["decision"] == "UNKNOWN"
    assert row["recommendation_eligibility"] == "UNKNOWN"
    assert row["verification_reason"] == "STRUCTURED_OUTPUT_ERROR"


def test_quality_gate_allows_only_accept():
    accepted = map_semantic_result(final_decision="ACCEPT", business_type="FOOD",
                                   location_scope="IN_SCOPE")
    rejected = map_semantic_result(final_decision="REJECT", business_type="NON_FOOD",
                                   location_scope="IN_SCOPE")
    unknown = technical_unknown("QWEN_TIMEOUT")
    assert downstream_allowed(accepted)
    assert not downstream_allowed(rejected)
    assert not downstream_allowed(unknown)
    assert recommendation_eligibility(accepted) == "ELIGIBLE"
    assert recommendation_eligibility(rejected) == "INELIGIBLE"
    assert recommendation_eligibility(unknown) == "UNKNOWN"


def test_rejection_cache_requires_unchanged_source_fingerprint():
    source = {"external_merchant_id": "m1", "name": "가게", "address": "논현동 1"}
    same = source_fingerprint(source)
    changed = source_fingerprint({**source, "name": "변경 가게"})
    rejected = map_semantic_result(final_decision="REJECT", business_type="NON_FOOD",
                                   location_scope="IN_SCOPE")
    assert can_reuse_rejection(rejected, same, same)
    assert not can_reuse_rejection(rejected, same, changed)


def test_rejection_cache_requires_matching_search_policy_when_versioned():
    source = {"external_merchant_id": "m1", "name": "가게", "address": "논현동 1"}
    fingerprint = source_fingerprint(source)
    rejected = map_semantic_result(
        final_decision="REJECT", business_type="FOOD", location_scope="OUT_OF_SCOPE"
    )
    assert can_reuse_rejection(rejected, fingerprint, fingerprint, "v1", "v1")
    assert not can_reuse_rejection(rejected, fingerprint, fingerprint, "v1", "v2")
    # 정책 버전이 없는 legacy cache는 versioned 현재 정책의 cache로 재사용하지 않는다.
    assert not can_reuse_rejection(rejected, fingerprint, fingerprint, None, "v1")


def test_no_candidate_and_provider_errors_are_unknown():
    for reason in ("NO_CANDIDATE", "HTTP_503", "QWEN_TIMEOUT", "STRUCTURED_OUTPUT_ERROR"):
        result = technical_unknown(reason)
        assert result.decision is VerificationDecision.UNKNOWN


def test_unknown_reason_kind_preserves_existing_contract_without_new_db_state():
    assert unknown_reason_kind("SEMANTIC_UNCERTAIN") == "SEMANTIC"
    assert unknown_reason_kind("NO_CANDIDATE") == "RETRIEVAL"
    assert unknown_reason_kind("STRUCTURED_OUTPUT_ERROR") == "TECHNICAL"
    assert unknown_reason_kind("HTTP_503") == "TECHNICAL"
