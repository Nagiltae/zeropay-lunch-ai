from app.place_resolver import RestaurantReference
from app.provider_entity_resolution_cli import evaluate_reference


class _FailingProvider:
    def search(self, *args, **kwargs):
        raise AssertionError("provider must be skipped for an unchanged cached rejection")


class _FailingMatcher:
    def choose(self, *args, **kwargs):
        raise AssertionError("Qwen must be skipped for an unchanged cached rejection")


def _reference():
    return RestaurantReference(
        restaurant_id=1,
        komsco_name="테스트 식당",
        komsco_address="서울 강남구 논현동 1",
        komsco_latitude=37.5,
        komsco_longitude=127.0,
        legal_dong="논현동",
        external_merchant_id="merchant-1",
    )


def test_unchanged_reject_skips_provider_and_qwen():
    from app.provider_entity_resolution_cli import _source
    from app.verification_quality_gate import source_fingerprint

    fingerprint = source_fingerprint(_source(_reference()))
    row = evaluate_reference(
        _reference(),
        _FailingProvider(),
        _FailingProvider(),
        _FailingMatcher(),
        {
            "decision": "REJECT",
            "verification_reason": "OUT_OF_SCOPE",
            "source_fingerprint": fingerprint,
        },
    )
    assert row["decision"] == "REJECT"
    assert row["recommendation_eligibility"] == "INELIGIBLE"
    assert row["provider_calls_skipped"] == "true"
    assert row["qwen_calls_skipped"] == "true"


def test_changed_fingerprint_does_not_reuse_reject():
    class _Provider:
        def search(self, *args, **kwargs):
            return type("Result", (), {"candidates": (), "error": "NO_CANDIDATE"})()

    row = evaluate_reference(
        _reference(), _Provider(), _Provider(), _FailingMatcher(),
        {"decision": "REJECT", "verification_reason": "OUT_OF_SCOPE", "source_fingerprint": "changed"},
    )
    assert row["provider_calls_skipped"] == "false"
    assert row["qwen_calls_skipped"] == "false"
