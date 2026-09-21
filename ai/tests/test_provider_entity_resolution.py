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


def test_provider_cli_prints_live_progress_without_external_calls(monkeypatch, tmp_path, capsys):
    import sys
    from app import provider_entity_resolution_cli as cli

    references = (_reference(), RestaurantReference(
        2, "둘째 식당", "서울 강남구 논현동 2", None, None, "논현동", "merchant-2",
    ))
    monkeypatch.setattr(cli, "load_local_env", lambda root: None)
    monkeypatch.setattr(cli, "load_provider_manifest", lambda path: references)
    monkeypatch.setattr(cli, "KakaoPlaceSearchProvider", lambda: object())
    monkeypatch.setattr(cli, "NaverPlaceSearchProvider", lambda: object())
    monkeypatch.setattr(cli, "OllamaClient", lambda: object())
    monkeypatch.setattr(cli, "QwenCandidateMatcher", lambda client: object())

    def fake_evaluate(reference, *args):
        row = cli._base(reference, "fingerprint")
        row["decision"] = "REJECT" if reference.restaurant_id == 1 else "ACCEPT"
        row["qwen_calls_skipped"] = "true" if reference.restaurant_id == 1 else "false"
        row["kakao_candidate_count"] = "0" if reference.restaurant_id == 1 else "1"
        return row

    monkeypatch.setattr(cli, "evaluate_reference", fake_evaluate)
    output = tmp_path / "result.csv"
    monkeypatch.setattr(sys, "argv", ["provider", "--manifest", str(tmp_path / "manifest.csv"),
                                      "--output", str(output)])
    assert cli.main() == 0
    printed = capsys.readouterr().out
    assert "current 1/2 id=1 name=테스트 식당" in printed
    assert "current 2/2 id=2 name=둘째 식당" in printed
    assert "2/2 (100.0%)" in printed
    assert "cache skip: 1" in printed
    assert "Qwen 호출 음식점: 1" in printed
    assert "ACCEPT: 1" in printed
    assert "REJECT: 1" in printed
    assert output.exists()
