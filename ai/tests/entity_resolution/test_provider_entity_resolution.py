"""Provider 후보 병합·prefetch·Qwen Entity Resolution 경계를 검증한다."""

import pytest

from app.entity_resolution.provider_entity_resolution_cli import (
    ProviderBatchResult,
    ProviderPrefetch,
    _fallback_query_variants,
    _merge_with_stats,
    _provider_query_rounds,
    _should_expand_search,
    evaluate_reference,
)
from app.entity_resolution.qwen_candidate_matcher import QwenDecision, QwenSemanticDecision
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
    from app.entity_resolution.provider_entity_resolution_cli import SEARCH_POLICY_VERSION, _source
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
            "search_policy_version": SEARCH_POLICY_VERSION,
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


def test_qwen_http_429_uses_blocked_cooldown_instead_of_unknown_ttl():
    class _Provider:
        def search(self, *args, **kwargs):
            return ProviderSearchResult("KAKAO", "테스트 식당", (PlaceSearchCandidate(
                "KAKAO", "1", "테스트 식당", "한식", "서울 강남구 논현동 1",
                "", 127.0, 37.5, "", "", "", {},
            ),), "")

    class _BlockedMatcher:
        def choose(self, *args, **kwargs):
            raise RuntimeError("HTTP_429")

    with pytest.raises(RuntimeError, match="BLOCKED: HTTP_429"):
        evaluate_reference(_reference(), _Provider(), _Provider(), _BlockedMatcher())


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


def test_provider_prefetch_round_one_uses_provider_specific_query():
    class _Provider:
        def __init__(self, provider):
            self.provider = provider
            self.queries = []

        def search(self, query, **kwargs):
            self.queries.append(query)
            return ProviderSearchResult(self.provider, query, ())

        def close(self):
            pass

    kakao = _Provider("KAKAO")
    naver = _Provider("NAVER_LOCAL")
    prefetch = ProviderPrefetch(kakao, naver, queue_size=1)
    pending = prefetch.submit(_reference(), round_number=1)
    prefetch.result(pending)
    prefetch.close()
    assert kakao.queries == ["테스트 식당"]
    assert naver.queries == ["논현동 테스트 식당"]


def test_adaptive_provider_rounds_start_with_provider_specific_query():
    rounds = _provider_query_rounds(_reference(), "KAKAO")
    naver_rounds = _provider_query_rounds(_reference(), "NAVER_LOCAL")
    assert rounds == (("테스트 식당",), ("논현동 테스트 식당",))
    assert naver_rounds == (("논현동 테스트 식당",), ("테스트 식당",))


def test_fallback_keeps_branch_name_and_only_strips_explicit_corporate_prefix():
    assert _fallback_query_variants("임명 진오돌뼈 본점") == ("임명 진오돌뼈", "진오돌뼈")
    assert _fallback_query_variants("(주)에스지푸드 논현역 마성떡볶이") == (
        "마성떡볶이 논현역",
    )


def test_round_two_only_expands_unresolved_round_one_result():
    assert _should_expand_search({"decision": "UNKNOWN", "qwen_calls_skipped": "false"})
    assert _should_expand_search({"decision": "REJECT", "qwen_calls_skipped": "false"})
    assert not _should_expand_search({"decision": "ACCEPT", "qwen_calls_skipped": "false"})
    assert not _should_expand_search({"decision": "REJECT", "qwen_calls_skipped": "true"})


def test_rejected_choose_top_n_expands_to_unchecked_candidates():
    candidates = tuple(
        PlaceSearchCandidate(
            "KAKAO", str(index), f"후보 {index}", "한식", f"서울 논현동 {index}",
            "", None, None, "", "", "", {},
        )
        for index in range(6)
    )
    provider_results = ProviderBatchResult(
        kakao=(ProviderSearchResult("KAKAO", "테스트 식당", candidates),),
        naver=(),
        provider_latency_seconds=0.0,
        prefetch_wait_seconds=0.0,
        prefetch_hit=True,
    )

    class Matcher:
        def __init__(self):
            self.choose_calls = 0
            self.validated_sizes = []

        def choose(self, reference, values):
            self.choose_calls += 1
            return QwenDecision(tuple(range(min(5, len(values)))), "HIGH")

        def validate_many(self, reference, values):
            self.validated_sizes.append(len(values))
            accepted = len(values) == 1
            return tuple(
                QwenSemanticDecision(
                    "MATCH" if accepted else "NO_MATCH",
                    "FOOD",
                    "IN_SCOPE" if accepted else "OUT_OF_SCOPE",
                    "ACCEPT" if accepted else "REJECT",
                    "", "", "", "", "same" if accepted else "branch",
                )
                for _ in values
            )

        def validate(self, reference, value):
            return self.validate_many(reference, (value,))[0]

    matcher = Matcher()
    row = evaluate_reference(
        _reference(), object(), object(), matcher, provider_results=provider_results
    )
    assert row["decision"] == "ACCEPT"
    assert row["kakao_selected_index"] == "5"
    assert matcher.choose_calls == 1
    assert matcher.validated_sizes == [5, 1]


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
