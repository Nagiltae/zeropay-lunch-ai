"""Provider 후보 병합·prefetch·Qwen Entity Resolution 경계를 검증한다."""

import pytest

from app.entity_resolution.provider_entity_resolution_cli import (
    ProviderPrefetch,
    _merge_with_stats,
    evaluate_reference,
)
from app.naver.place_resolver import RestaurantReference
from app.providers.place_provider import PlaceSearchCandidate, ProviderSearchResult


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
    from app.entity_resolution.provider_entity_resolution_cli import _source
    from app.entity_resolution.verification_quality_gate import source_fingerprint

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
        _reference(),
        _Provider(),
        _Provider(),
        _FailingMatcher(),
        {
            "decision": "REJECT",
            "verification_reason": "OUT_OF_SCOPE",
            "source_fingerprint": "changed",
        },
    )
    assert row["provider_calls_skipped"] == "false"
    assert row["qwen_calls_skipped"] == "false"


def test_provider_429_stops_before_other_provider_or_qwen():
    class _BlockedProvider:
        def search(self, *args, **kwargs):
            return type("Result", (), {"candidates": (), "error": "HTTP_429"})()

    with pytest.raises(RuntimeError, match="BLOCKED: kakao_error: HTTP_429"):
        evaluate_reference(_reference(), _BlockedProvider(), _FailingProvider(), _FailingMatcher())


def test_provider_merge_deduplicates_only_identical_same_provider_candidates():
    first = PlaceSearchCandidate(
        "NAVER_LOCAL",
        "",
        "식당",
        "한식",
        "서울 논현동 1",
        "논현로 1",
        127.0,
        37.5,
        "",
        "https://example.test/place/1",
        "",
        {},
    )
    duplicate = PlaceSearchCandidate(
        "NAVER_LOCAL",
        "",
        " 식당 ",
        "한식",
        "서울 논현동 1",
        "논현로 1",
        127.0,
        37.5,
        "",
        "https://example.test/place/1",
        "",
        {},
    )
    branch = PlaceSearchCandidate(
        "NAVER_LOCAL",
        "",
        "식당",
        "한식",
        "서울 논현동 2",
        "논현로 2",
        127.0,
        37.5,
        "",
        "https://example.test/place/2",
        "",
        {},
    )
    merged, before, removed = _merge_with_stats(
        (ProviderSearchResult("NAVER_LOCAL", "식당", (first, duplicate, branch)),)
    )
    assert (before, len(merged), removed) == (3, 2, 1)
    assert [candidate.detail_url for candidate in merged] == [
        "https://example.test/place/1",
        "https://example.test/place/2",
    ]


def test_provider_prefetch_keeps_two_variant_order_and_is_bounded():
    class _Provider:
        def __init__(self, provider):
            self.provider = provider
            self.queries = []
            self.closed = False

        def search(self, query, **kwargs):
            self.queries.append(query)
            return ProviderSearchResult(self.provider, query, ())

        def close(self):
            self.closed = True

    kakao = _Provider("KAKAO")
    naver = _Provider("NAVER_LOCAL")
    prefetch = ProviderPrefetch(kakao, naver, queue_size=1)
    pending = prefetch.submit(_reference())
    result = prefetch.result(pending)
    prefetch.close()
    assert kakao.queries == ["테스트 식당", "논현동 테스트 식당"]
    assert naver.queries == ["테스트 식당", "논현동 테스트 식당"]
    assert isinstance(result.prefetch_hit, bool)
    assert kakao.closed and naver.closed


def test_provider_cli_prints_live_progress_without_external_calls(monkeypatch, tmp_path, capsys):
    import sys

    from app.entity_resolution import provider_entity_resolution_cli as cli

    class LocalProgress(cli.BatchProgress):
        def __init__(self, stage, total, labels, **kwargs):
            super().__init__(stage, total, labels, report_dir=tmp_path)

    monkeypatch.setattr(cli, "BatchProgress", LocalProgress)

    references = (
        _reference(),
        RestaurantReference(
            2,
            "둘째 식당",
            "서울 강남구 논현동 2",
            None,
            None,
            "논현동",
            "merchant-2",
        ),
    )
    monkeypatch.setattr(cli, "load_local_env", lambda root: None)
    monkeypatch.setattr(cli, "load_provider_manifest", lambda path: references)

    class _Provider:
        provider = "KAKAO"

        def search(self, query, **kwargs):
            return ProviderSearchResult(self.provider, query, ())

        def close(self):
            pass

    class _NaverProvider(_Provider):
        provider = "NAVER_LOCAL"

    monkeypatch.setattr(cli, "KakaoPlaceSearchProvider", _Provider)
    monkeypatch.setattr(cli, "NaverPlaceSearchProvider", _NaverProvider)
    monkeypatch.setattr(cli, "OllamaClient", lambda: object())
    monkeypatch.setattr(cli, "QwenCandidateMatcher", lambda client, **kwargs: object())

    def fake_evaluate(reference, *args, **kwargs):
        row = cli._base(reference, "fingerprint")
        row["decision"] = "REJECT" if reference.restaurant_id == 1 else "ACCEPT"
        row["qwen_calls_skipped"] = "true" if reference.restaurant_id == 1 else "false"
        row["kakao_candidate_count"] = "0" if reference.restaurant_id == 1 else "1"
        return row

    monkeypatch.setattr(cli, "evaluate_reference", fake_evaluate)
    output = tmp_path / "result.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        ["provider", "--manifest", str(tmp_path / "manifest.csv"), "--output", str(output)],
    )
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
