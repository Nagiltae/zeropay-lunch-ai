from app import place_resolver_cli as cli
from app.place_resolver import (
    PlaceCandidate,
    ResolutionStatus,
    RestaurantReference,
    deterministic_fast_path,
    best_address_evidence,
    compare_address_pair,
    hard_rejection_reason,
    extract_candidate_place_ids,
    extract_place_id,
    extract_place_ids_from_nlog_params,
    normalize_text,
    normalize_name_for_match,
    query_variants_for,
    resolve_candidate,
)
from app.qwen_candidate_matcher import (
    QwenCandidateMatcher,
    QwenDecision,
    parse_qwen_decision,
)


def test_address_best_evidence_ignores_trailing_detail_and_mixed_sources() -> None:
    assert compare_address_pair(
        "서울특별시 강남구 도산대로30길 46 tov토브", "서울 강남구 도산대로30길 46"
    ) == "STRONG_MATCH"
    assert best_address_evidence(
        ("서울 강남구 논현동 80-6", "서울 강남구 학동로 123"),
        ("서울 강남구 학동로 123 2층", ""),
    ) == "STRONG_MATCH"


def test_address_missing_is_unknown_and_not_different() -> None:
    assert compare_address_pair("서울 강남구 학동로 123", "") == "UNKNOWN"
    assert best_address_evidence(("서울 강남구 학동로 123",), ("",)) == "UNKNOWN"


def test_semantic_address_parser_rejects_route_guidance() -> None:
    assert cli.parse_semantic_address_row(
        "주소", "주소 서울 강남구 도산대로30길 46"
    ) == "서울 강남구 도산대로30길 46"
    assert cli.parse_semantic_address_row(
        "주소", "주소 7수인분당강남구청역 3-1번 출구에서 592m"
    ) == ""


def test_live_address_rows_keep_road_jibun_and_route_separate() -> None:
    assert cli.parse_address_value_row(
        "도로명", "도로명서울 강남구 도산대로30길 46 tov토브복사"
    ) == "서울 강남구 도산대로30길 46 tov토브"
    assert cli.parse_address_value_row(
        "지번", "지번서울 강남구 논현동 80-6복사"
    ) == "서울 강남구 논현동 80-6"
    assert cli.parse_route_value_row(
        "찾아가는길", "찾아가는길학동역8번출구 도보10분"
    ) == "학동역8번출구 도보10분"
    assert cli.parse_route_value_row(
        "주소", "주소학동역8번출구 도보10분"
    ) == ""


def reference() -> RestaurantReference:
    return RestaurantReference(
        restaurant_id=1,
        komsco_name="테스트 식당",
        komsco_address="서울특별시 강남구 테헤란로 1",
        komsco_latitude=37.5,
        komsco_longitude=127.0,
        legal_dong="역삼동",
    )


def test_population_is_komsco_only_nonhyeon_without_naver_join(monkeypatch, tmp_path) -> None:
    seen = []

    def fake_rows(_root, sql):
        seen.append(sql)
        return [{
            "restaurant_id": 7,
            "name": "논현 식당",
            "address": "서울 강남구 논현동",
            "detail_address": "",
            "latitude": "37.51",
            "longitude": "127.03",
            "legal_dong_name": "논현동",
            "industry_name": "음식점",
        }]

    monkeypatch.setattr(cli, "_mysql_rows", fake_rows)
    population = cli.load_komsco_population(tmp_path, None)
    assert population.references[0].komsco_name == "논현 식당"
    assert "11680108" in seen[0]
    assert "restaurant_external_places" not in seen[0]
    assert "I0000002" not in seen[0]


def test_population_keeps_coordinate_null_komsco_row(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_mysql_rows", lambda _root, _sql: [{
        "restaurant_id": 8, "name": "좌표없는 식당", "address": "서울 강남구 논현동",
        "detail_address": "", "latitude": "", "longitude": "",
        "legal_dong_name": "논현동", "industry_name": "음식점",
    }])
    population = cli.load_komsco_population(tmp_path, None)
    assert len(population.references) == 1
    assert population.references[0].komsco_latitude is None
    assert population.references[0].komsco_longitude is None


def test_extracts_only_explicit_place_path() -> None:
    assert extract_place_id("https://map.naver.com/p/place/12345") == "12345"
    assert extract_place_id("https://map.naver.com/entry/place/12345?c=1") == "12345"
    assert (
        extract_place_id("https://pcmap.place.naver.com/restaurant/1126763661/home") == "1126763661"
    )
    assert extract_place_id("/restaurant/1126763661/home") == "1126763661"
    assert extract_place_id("/place/1126763661") == "1126763661"
    assert extract_place_id("/entry/place/1126763661") == "1126763661"
    assert extract_place_id("https://map.naver.com/p/search/test") is None


def test_resolves_exact_name_and_address() -> None:
    candidate = PlaceCandidate(
        "테스트 식당",
        "서울특별시 강남구 테헤란로 1",
        "음식점>한식",
        "https://map.naver.com/p/place/12345",
        "12345",
        37.5,
        127.0,
    )
    result = resolve_candidate(reference(), [candidate])
    assert result.status == ResolutionStatus.RESOLVED
    assert result.candidate.place_id == "12345"


def test_name_match_ignores_observed_legal_and_category_suffixes() -> None:
    candidate = PlaceCandidate(
        "상해루중식당",
        "서울 강남구 강남대로 512 지하1층",
        "중식당",
        "",
        "12345",
    )
    source = RestaurantReference(
        2, "(주)상해루", "서울 강남구 강남대로 512 지하1층 (논현동)", 37.5, 127.0, "논현동"
    )
    assert normalize_name_for_match("(주)상해루") == "상해루"
    assert resolve_candidate(source, [candidate]).status == ResolutionStatus.RESOLVED


def test_query_variants_are_deterministic_and_kosmsco_only() -> None:
    values = query_variants_for(
        RestaurantReference(3, "(주)상해루", "서울 강남구 강남대로 512, 지하1층 (논현동)", None, None, "논현동")
    )
    assert values[0] == "논현동 (주)상해루"
    assert "논현동 상해루" in values
    assert any("강남대로 512" in value for value in values)
    assert values[-1] == "상해루"


def test_qwen_receives_bounded_soft_ranked_pool_larger_than_top_five(monkeypatch) -> None:
    reference_value = reference()
    candidates = tuple(
        cli.CandidateDom(
            cli.PlaceCandidate(f"테스트 식당 후보{i}", "서울 강남구 테헤란로 99", "한식", "", str(i)),
            object(), i, (str(i),)
        )
        for i in range(8)
    )
    monkeypatch.setattr(cli, "search_direct", lambda *_args, **_kwargs: (candidates, 8))
    monkeypatch.setattr(cli, "rank_candidates", lambda _reference, values: tuple(values))
    monkeypatch.setattr(cli, "deterministic_fast_path", lambda *_args: None)
    monkeypatch.setattr(
        cli, "load_detail_page",
        lambda *_args, **_kwargs: cli.DetailData(
            "/restaurant/1/home", "다른 식당", "서울 강남구 테헤란로 99", "한식"
        ),
    )
    seen = []
    matcher = type(
        "Matcher", (), {
            "choose": lambda self, _reference, values: (
                seen.append(len(values))
                or type("Decision", (), {"candidate_indices": (0, 1, 2, 3, 4), "confidence": "LOW"})()
            )
        }
    )()
    result = cli.run_one(object(), reference_value, "query", "KOMSCO", matcher)
    assert seen == [8]
    assert result.qwen_candidate_indices == (0, 1, 2, 3, 4)
    assert result.resolution.status is cli.ResolutionStatus.AMBIGUOUS
    assert result.detail_validation_attempts == 5


def test_qwen_rank_one_failure_continues_to_rank_two(monkeypatch) -> None:
    source = reference()
    first = cli.CandidateDom(
        cli.PlaceCandidate(source.komsco_name, source.komsco_address, "한식", "", "111"),
        object(), 0, ("111",)
    )
    second = cli.CandidateDom(
        cli.PlaceCandidate(source.komsco_name, source.komsco_address, "한식", "", "222"),
        object(), 1, ("222",)
    )
    monkeypatch.setattr(cli, "search_direct", lambda *_args, **_kwargs: ((first, second), 2))
    monkeypatch.setattr(cli, "rank_candidates", lambda _reference, values: tuple(values))
    monkeypatch.setattr(cli, "deterministic_fast_path", lambda *_args: None)
    def detail(_page, candidate, **_kwargs):
        if candidate.place_id == "111":
            return cli.DetailData("/restaurant/111/home", "전혀 다른 곳", "서울 강남구 다른로 9", "한식")
        return cli.DetailData("/restaurant/222/home", source.komsco_name, source.komsco_address, "한식")
    monkeypatch.setattr(cli, "load_detail_page", detail)
    matcher = type(
        "Matcher", (), {
            "choose": lambda self, _reference, _values: type(
                "Decision", (), {"candidate_indices": (0, 1), "confidence": "HIGH"}
            )()
        }
    )()
    result = cli.run_one(object(), source, "query", "KOMSCO", matcher)
    assert result.resolution.status is cli.ResolutionStatus.RESOLVED
    assert result.place_id == "222"
    assert result.detail_validation_attempts == 2


def test_prefers_unresolved_when_name_or_address_does_not_support_identity() -> None:
    candidate = PlaceCandidate(
        "다른 식당",
        "서울특별시 강남구 테헤란로 99",
        "음식점>한식",
        "https://map.naver.com/p/place/99999",
        "99999",
        37.5,
        127.0,
    )
    result = resolve_candidate(reference(), [candidate])
    assert result.status == ResolutionStatus.NOT_FOUND
    assert result.candidate.place_id == "99999"
    assert normalize_text(" <b>테스트 식당</b> ") == "테스트식당"


def test_place_id_with_insufficient_address_evidence_is_ambiguous() -> None:
    candidate = PlaceCandidate(
        "테스트 식당",
        "",
        "음식점>한식",
        "https://map.naver.com/p/place/12345",
        "12345",
    )
    result = resolve_candidate(reference(), [candidate])
    assert result.status == ResolutionStatus.AMBIGUOUS
    assert result.candidate.place_id == "12345"


def test_optional_category_and_coordinates_are_unknown_not_reject() -> None:
    candidate = PlaceCandidate("테스트 식당", "", "", "", "12345")
    result = resolve_candidate(reference(), [candidate])
    assert result.status == ResolutionStatus.AMBIGUOUS
    assert hard_rejection_reason(reference(), candidate) is None


def test_only_clear_non_food_or_both_name_and_address_mismatch_is_rejected() -> None:
    non_food = PlaceCandidate("테스트 식당", "서울 강남구 테헤란로 1", "건강,의료>약국", "", "1")
    mismatch = PlaceCandidate("전혀 다른 곳", "서울 강남구 테헤란로 99", "", "", "2")
    assert hard_rejection_reason(reference(), non_food) == "NON_FOOD_CATEGORY"
    assert hard_rejection_reason(reference(), mismatch) == "NAME_AND_ADDRESS_MISMATCH"


def test_extracts_place_id_from_encoded_nlog_params() -> None:
    value = "{&quot;place_id&quot;:&quot;38648810&quot;,&quot;name&quot;:&quot;토브버거,TOV&quot;}"
    assert extract_place_ids_from_nlog_params(value) == ("38648810",)
    assert extract_candidate_place_ids([value, value]) == ("38648810",)


def test_rejects_mixed_or_non_numeric_candidate_ids() -> None:
    first = '{"place_id":"38648810"}'
    second = '{"place_id":"38648811"}'
    assert extract_candidate_place_ids([first, second]) == ()
    assert extract_place_ids_from_nlog_params('{"place_id":"not-an-id"}') == ()


class FakeLlm:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str, schema: dict) -> str:
        self.calls += 1
        self.system = system
        self.user = user
        self.schema = schema
        return self.response


def test_qwen_decision_is_schema_and_range_checked() -> None:
    assert parse_qwen_decision(
        '{"candidateIndices": [0], "confidence": "HIGH"}', 1
    ) == QwenDecision((0,), "HIGH")
    for raw in (
        "not-json",
        '{"candidateIndices": [2], "confidence": "HIGH"}',
        '{"candidateIndices": [], "confidence": "LOW"}',
    ):
        try:
            parse_qwen_decision(raw, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid Qwen response must fail closed")


def test_qwen_prompt_never_contains_place_id() -> None:
    fake = FakeLlm('{"candidateIndices": [0], "confidence": "HIGH"}')
    matcher = QwenCandidateMatcher(fake)
    candidate = PlaceCandidate("테스트 식당", "서울 강남구 테헤란로 1", "한식", "", "38648810")
    decision = matcher.choose(reference(), [candidate])
    assert decision == QwenDecision((0,), "HIGH")
    assert "38648810" not in fake.user
    assert "place_id" not in fake.user
    assert fake.schema["properties"]["candidateIndices"]["items"]["enum"] == [0]


def test_dynamic_qwen_schema_limits_candidate_indices() -> None:
    fake = FakeLlm('{"candidateIndices": [1, 0, 2], "confidence": "LOW"}')
    matcher = QwenCandidateMatcher(fake)
    candidates = [
        PlaceCandidate("첫 식당", "서울 강남구 테헤란로 1", "한식", "", "1"),
        PlaceCandidate("둘 식당", "서울 강남구 테헤란로 2", "한식", "", "2"),
        PlaceCandidate("셋 식당", "서울 강남구 테헤란로 3", "한식", "", "3"),
    ]
    assert matcher.choose(reference(), candidates) == QwenDecision((1, 0, 2), "LOW")
    assert fake.schema["properties"]["candidateIndices"]["items"]["enum"] == [0, 1, 2]


def test_qwen_ranks_all_candidates_up_to_top_five() -> None:
    fake = FakeLlm('{"candidateIndices": [4, 3, 2, 1, 0], "confidence": "LOW"}')
    matcher = QwenCandidateMatcher(fake)
    candidates = [PlaceCandidate(f"식당{i}", "주소", "한식", "", str(i)) for i in range(5)]
    assert matcher.choose(reference(), candidates).candidate_indices == (4, 3, 2, 1, 0)
    schema = fake.schema["properties"]["candidateIndices"]
    assert schema["minItems"] == 5
    assert schema["maxItems"] == 5
    assert schema["uniqueItems"] is True


def test_two_candidates_require_both_ranked_indices() -> None:
    fake = FakeLlm('{"candidateIndices": [1, 0], "confidence": "HIGH"}')
    matcher = QwenCandidateMatcher(fake)
    candidates = [
        PlaceCandidate("첫 식당", "서울 강남구 테헤란로 1", "한식", "", "1"),
        PlaceCandidate("둘 식당", "서울 강남구 테헤란로 2", "한식", "", "2"),
    ]
    assert matcher.choose(reference(), candidates) == QwenDecision((1, 0), "HIGH")
    schema = fake.schema["properties"]["candidateIndices"]
    assert schema["minItems"] == 2
    assert schema["maxItems"] == 2
    assert schema["uniqueItems"] is True
    assert fake.schema["required"] == ["candidateIndices", "confidence"]


def test_qwen_retry_is_bounded_to_one_retry() -> None:
    fake = FakeLlm('{"candidateIndices": [99], "confidence": "HIGH"}')
    matcher = QwenCandidateMatcher(fake)
    try:
        matcher.choose(reference(), [PlaceCandidate("식당", "주소", "한식", "", "1")])
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range response must fail")
    assert fake.calls == 2


def test_strong_single_candidate_uses_safe_fast_path() -> None:
    candidate = PlaceCandidate(
        "테스트 식당", "서울특별시 강남구 테헤란로 1", "음식점>한식", "", "1"
    )
    assert deterministic_fast_path(reference(), [candidate]) == candidate


def test_fast_path_rejects_branch_conflict_and_runner_up() -> None:
    branch = PlaceCandidate(
        "테스트 식당 역삼점", "서울특별시 강남구 테헤란로 99", "음식점>한식", "", "1"
    )
    exact = PlaceCandidate("테스트 식당", "서울특별시 강남구 테헤란로 1", "음식점>한식", "", "2")
    assert deterministic_fast_path(reference(), [branch]) is None
    assert deterministic_fast_path(reference(), [exact, branch]) is None


def test_verified_checkpoint_round_trip(tmp_path) -> None:
    result = type(
        "Result", (), {
            "resolution": type("Resolution", (), {"status": ResolutionStatus.RESOLVED})(),
            "place_id": "38648810",
            "reference": reference(),
            "detail": type("Detail", (), {"name": "토브버거", "address": "서울 강남구 도산대로30길 46"})(),
            "candidate": None,
        },
    )()
    path = tmp_path / "verified.csv"
    cli.save_verified_checkpoint(path, result)
    loaded = cli.load_verified_checkpoint(path)
    assert loaded[1]["place_id"] == "38648810"
    assert loaded[1]["verification_status"] == "RESOLVED"
def test_resume_rejects_non_komsco_output(tmp_path) -> None:
    report = tmp_path / "legacy.csv"
    report.write_text("restaurant_id,final_status\n1,RESOLVED\n", encoding="utf-8")
    writer = cli.ReportWriter(report, resume=True)
    try:
        try:
            writer.completed_ids()
        except RuntimeError as error:
            assert "KOMSCO-direct" in str(error)
        else:
            raise AssertionError("legacy input population must not be resumed")
    finally:
        writer.close()


def test_db_apply_uses_only_resolved_numeric_place_ids(tmp_path, monkeypatch) -> None:
    report = tmp_path / "komsco.csv"
    report.write_text(
        "source_type,restaurant_id,final_status,detail_validation,place_id\n"
        "KOMSCO_ONLY,1,RESOLVED,PASS,12345\n"
        "KOMSCO_ONLY,2,AMBIGUOUS,PASS,23456\n"
        "KOMSCO_ONLY,3,RESOLVED,FAIL,34567\n"
        "KOMSCO_ONLY,4,RESOLVED,PASS,not-numeric\n",
        encoding="utf-8",
    )
    calls = []

    def fake_write(_root, restaurant_id, place_id, **_metadata):
        calls.append((restaurant_id, place_id))
        return True

    monkeypatch.setattr(cli, "_write_place_mapping", fake_write)
    assert cli.apply_resolved_csv_to_db(report, cli.Path(".")) == (1, 0)
    assert calls == [(1, "12345")]


def test_place_mapping_insert_and_update_are_idempotent_sql_paths(monkeypatch) -> None:
    commands = []

    class Completed:
        returncode = 0
        stdout = "1\n"
        stderr = ""

    monkeypatch.setattr(cli.subprocess, "run", lambda command, **_kwargs: commands.append(command) or Completed())
    monkeypatch.setattr(cli, "_mysql_rows", lambda _root, _sql: [])
    assert cli._write_place_mapping(cli.Path("."), 1, "12345", external_name="식당") is True
    insert_sql = commands[-1][-1]
    assert "INSERT INTO restaurant_external_places" in insert_sql
    assert "external_place_id" in insert_sql

    def existing_rows(_root, sql):
        if "external_place_id" in sql:
            return [{"restaurant_id": 1}]
        return [{"id": 7}]

    monkeypatch.setattr(cli, "_mysql_rows", existing_rows)
    assert cli._write_place_mapping(cli.Path("."), 1, "12345") is True
    assert "UPDATE restaurant_external_places SET" in commands[-1][-1]


def test_place_mapping_rejects_place_id_owned_by_another_restaurant(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_mysql_rows", lambda _root, _sql: [{"restaurant_id": 2}])
    try:
        cli._write_place_mapping(cli.Path("."), 1, "12345")
    except RuntimeError as error:
        assert "already mapped" in str(error)
    else:
        raise AssertionError("a Place ID must not be remapped to another restaurant")


def test_candidate_locator_timeout_is_recorded_and_top_k_continues(monkeypatch) -> None:
    reference = cli.RestaurantReference(
        restaurant_id=4375,
        komsco_name="테스트 식당",
        komsco_address="서울 강남구 테스트로 1",
        komsco_latitude=None,
        komsco_longitude=None,
        legal_dong="개포동",
    )
    first = cli.CandidateDom(
        cli.PlaceCandidate("테스트 식당 1", "", "음식점", "", "111"), object(), 0, ("111",)
    )
    second = cli.CandidateDom(
        cli.PlaceCandidate("테스트 식당 2", "서울 강남구 테스트로 1", "음식점", "", "222"), object(), 1, ("222",)
    )
    monkeypatch.setattr(cli, "search_direct", lambda *_args, **_kwargs: ((first, second), 2))
    timeout = cli.PlaywrightTimeoutError("address locator timeout")
    detail = cli.DetailData("/restaurant/222/home", "테스트 식당 2", "서울 강남구 테스트로 1", "음식점")
    def fake_load_detail(*_args, **_kwargs):
        candidate = _args[1]
        if candidate.place_id == "111":
            raise timeout
        return detail

    monkeypatch.setattr(cli, "load_detail_page", fake_load_detail)
    resolve_calls = []

    def fake_resolve(ref, candidates):
        resolve_calls.append(1)
        return cli.Resolution(
            ref,
            "query",
            candidates[0],
            cli.ResolutionStatus.AMBIGUOUS if len(resolve_calls) == 1 else cli.ResolutionStatus.RESOLVED,
            "EXACT",
            "STRONG_MATCH",
            "UNKNOWN",
            (),
        )

    monkeypatch.setattr(cli, "resolve_candidate", fake_resolve)
    monkeypatch.setattr(cli, "deterministic_fast_path", lambda *_args: None)
    monkeypatch.setattr(cli, "rank_candidates", lambda _reference, candidates: candidates)
    matcher = type(
        "Matcher",
        (),
        {"choose": lambda self, _reference, _candidates: type("Decision", (), {"candidate_indices": (0, 1), "confidence": "HIGH"})()},
    )()
    result = cli.run_one(object(), reference, "query", "KOMSCO", matcher)
    assert result.resolution.status is cli.ResolutionStatus.RESOLVED
    assert result.place_id == "222"
    assert result.detail_validation_attempts == 2
    assert result.validation_attempts_detail[0].failure_reason == "LOCATOR_TIMEOUT"


def test_resume_write_db_is_apply_only_and_never_starts_resolver(tmp_path, monkeypatch) -> None:
    report = tmp_path / "reviewed.csv"
    report.write_text(
        "source_type,restaurant_id,final_status,detail_validation,place_id\n"
        "KOMSCO_ONLY,1,RESOLVED,PASS,12345\n",
        encoding="utf-8",
    )
    applied = []
    preflight_modes = []

    monkeypatch.setattr(
        cli,
        "preflight",
        lambda _root, _output, require_db, **_kwargs: preflight_modes.append(require_db),
    )
    monkeypatch.setattr(
        cli,
        "load_komsco_population",
        lambda _root, _limit: cli.KomscoPopulation((), 0),
    )
    monkeypatch.setattr(cli, "apply_resolved_csv_to_db", lambda _path, _root: (applied.append(1) or (1, 0)))

    def fail_if_browser_starts():
        raise AssertionError("CSV apply mode must not start Playwright")

    monkeypatch.setattr(cli, "sync_playwright", fail_if_browser_starts)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["place_resolver_cli", "--output", str(report), "--resume", "--write-db"],
    )

    assert cli.main() == 0
    assert applied == [1]
    assert preflight_modes == [True]


def test_csv_only_mode_does_not_apply_db_or_start_for_empty_fixture(tmp_path, monkeypatch) -> None:
    report = tmp_path / "csv-only.csv"
    applied = []
    monkeypatch.setattr(cli, "preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "load_komsco_population",
        lambda _root, _limit: cli.KomscoPopulation((), 0),
    )
    monkeypatch.setattr(cli, "apply_resolved_csv_to_db", lambda *_args: applied.append(1))
    monkeypatch.setattr(cli, "sync_playwright", lambda: (_ for _ in ()).throw(AssertionError("no resolver")))
    monkeypatch.setattr(cli.sys, "argv", ["place_resolver_cli", "--output", str(report), "--dry-run"])

    assert cli.main() == 0
    assert applied == []
