from app.verification_quality_gate import (
    VerificationDecision, can_reuse_rejection, downstream_allowed,
    map_semantic_result, recommendation_eligibility, source_fingerprint,
    technical_unknown,
)


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


def test_no_candidate_and_provider_errors_are_unknown():
    for reason in ("NO_CANDIDATE", "HTTP_503", "QWEN_TIMEOUT", "STRUCTURED_OUTPUT_ERROR"):
        result = technical_unknown(reason)
        assert result.decision is VerificationDecision.UNKNOWN
