"""ACCEPT Canonical SQL과 음식점 단위 persistence transaction을 검증한다."""

import csv

import pytest

from app.canonical import canonical_persistence_cli
from app.canonical.canonical_builder import _sql_value, build_canonical, generate_mapping_sql
from app.canonical.canonical_persistence_cli import process_csv, verification_metadata
from app.naver.place_detail_persistence import PlaceDetailPersistence
from app.naver.place_resolver import RestaurantReference
from app.providers.place_provider import PlaceSearchCandidate


def test_build_canonical_with_provider_name_and_category():
    reference = RestaurantReference(
        restaurant_id=1,
        komsco_name="원조맛집",
        komsco_address="서울 강남구 논현동 1",
        komsco_latitude=37.1,
        komsco_longitude=127.1,
        legal_dong="논현동",
        external_merchant_id="merchant-1",
    )
    candidate = PlaceSearchCandidate(
        provider="NAVER",
        external_place_id="naver-1",
        name="진짜원조맛집",
        category="한식 > 국밥",
        address="서울 강남구 논현동 1-1",
        road_address="서울 강남구 강남대로 123",
        latitude=37.2,
        longitude=127.2,
        phone="",
        detail_url="",
        distance="",
        raw_metadata={},
    )

    canonical = build_canonical(reference, candidate)
    assert canonical.restaurant_id == 1
    assert canonical.name == "진짜원조맛집"  # Uses provider name
    assert canonical.category == "한식 > 국밥"  # Uses provider category
    assert canonical.address == "서울 강남구 논현동 1"  # Uses KOMSCO base address
    assert canonical.road_address == "서울 강남구 강남대로 123"  # Uses provider road address
    assert canonical.latitude == 37.2
    assert canonical.longitude == 127.2


def test_build_canonical_fallback_to_komsco():
    reference = RestaurantReference(
        restaurant_id=2,
        komsco_name="KOMSCO Name",
        komsco_address="KOMSCO Address",
        komsco_latitude=37.1,
        komsco_longitude=127.1,
        legal_dong="논현동",
        external_merchant_id="merchant-2",
    )
    candidate = PlaceSearchCandidate(
        provider="KAKAO",
        external_place_id="kakao-2",
        name="",  # Missing name
        category="",
        address="Provider Address",
        road_address="",  # Missing road address
        latitude=None,  # Missing lat
        longitude=None,  # Missing lon
        phone="",
        detail_url="",
        distance="",
        raw_metadata={},
    )

    canonical = build_canonical(reference, candidate)
    assert canonical.name == "KOMSCO Name"
    assert canonical.category == ""
    assert canonical.address == "KOMSCO Address"
    assert canonical.road_address == "Provider Address"  # Falls back to candidate.address
    assert canonical.latitude == 37.1
    assert canonical.longitude == 127.1


def test_sql_value_empty_string_becomes_null():
    """빈 문자열 external_place_id는 NULL로 저장되어야 한다."""
    assert _sql_value(None) == "NULL"
    assert _sql_value("") == "NULL"
    assert _sql_value("12345") == "'12345'"
    assert _sql_value(100.0) == "100.0"


def test_generate_mapping_sql_empty_place_id_stores_null():
    """NAVER_LOCAL처럼 Place ID가 없는 후보는 external_place_id=NULL로 INSERT된다."""
    candidate = PlaceSearchCandidate(
        provider="NAVER_LOCAL",
        external_place_id="",  # 빈 문자열
        name="테스트식당",
        category="한식",
        address="서울 강남구 논현동 1",
        road_address="서울 강남구 강남대로 1",
        latitude=37.5,
        longitude=127.0,
        phone="",
        detail_url="",
        distance="",
        raw_metadata={},
    )
    sql = generate_mapping_sql(999, candidate)
    # external_place_id 위치에 NULL이 들어가야 함 (빈 문자열 '' 아님)
    assert "NULL" in sql
    assert "''" not in sql.split("VALUES")[1].split(",")[2]  # 3번째 컬럼 = external_place_id


def test_verification_metadata_uses_provider_reason_and_configured_model(monkeypatch):
    monkeypatch.setenv("QWEN_MODEL", "qwen3.5:9b")
    status, reason, model = verification_metadata(
        {
            "decision": "REJECT",
            "verification_reason": "OUT_OF_SCOPE",
            "reason": "must not be used",
        }
    )
    assert status == "REJECTED"
    assert reason == "OUT_OF_SCOPE"
    assert model == "qwen3.5:9b"


def test_verification_metadata_preserves_actual_inference_model(monkeypatch):
    monkeypatch.setenv("QWEN_MODEL", "qwen3.5:9b")
    _, _, model = verification_metadata(
        {
            "decision": "REJECT",
            "verification_reason": "NO_MATCH",
            "qwen_model": "model-recorded-in-result",
        }
    )
    assert model == "model-recorded-in-result"


def test_verification_metadata_normalizes_long_reason_to_structured_code():
    status, reason, _ = verification_metadata(
        {
            "decision": "REJECT",
            "verification_reason": "자연어 판단 사유 " * 20,
            "qwen_business_type": "NON_FOOD",
            "qwen_location_scope": "IN_SCOPE",
        }
    )
    assert status == "REJECTED"
    assert reason == "NON_FOOD"


def test_persistence_accepts_csv_source_fingerprint(monkeypatch, tmp_path):
    persistence = PlaceDetailPersistence(tmp_path)
    captured = []
    monkeypatch.setattr(persistence, "_run", captured.append)
    persistence.persist_verification(
        restaurant_id=1,
        status="REJECTED",
        reason="OUT_OF_SCOPE",
        place_id=None,
        model_name="qwen3.5:9b",
        source_fingerprint_value="fingerprint-from-csv",
        eligibility="INELIGIBLE",
    )
    assert "'fingerprint-from-csv'" in captured[0]


def test_canonical_is_written_before_verified_checkpoint(monkeypatch, tmp_path):
    import csv
    import json

    from app.canonical import canonical_persistence_cli

    path = tmp_path / "result.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "restaurant_id",
                "external_merchant_id",
                "komsco_name",
                "komsco_address",
                "decision",
                "naver_selected_index",
                "kakao_selected_index",
                "candidates_json",
                "source_fingerprint",
                "recommendation_eligibility",
                "verification_reason",
                "qwen_model",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "restaurant_id": "1",
                "external_merchant_id": "merchant-1",
                "komsco_name": "음식점",
                "komsco_address": "논현동 1",
                "decision": "ACCEPT",
                "naver_selected_index": "0",
                "candidates_json": json.dumps(
                    [
                        {
                            "provider": "NAVER_LOCAL",
                            "external_place_id": "",
                            "name": "음식점",
                            "address": "논현동 1",
                            "category": "한식",
                        }
                    ]
                ),
                "source_fingerprint": "fingerprint",
                "recommendation_eligibility": "ELIGIBLE",
                "verification_reason": "MATCHED",
                "qwen_model": "qwen3.5:9b",
            }
        )

    events = []
    monkeypatch.setattr(
        canonical_persistence_cli,
        "_execute_sql",
        lambda _, sql: events.append(("transaction", sql)),
    )
    monkeypatch.setattr(
        PlaceDetailPersistence,
        "verification_sql",
        lambda *_, **__: events.append("verification") or "UPDATE verification_marker;",
    )
    assert process_csv(path, tmp_path) == (1, 0)
    assert events[0] == "verification"
    assert events[1][0] == "transaction"
    assert "INSERT INTO canonical_restaurants" in events[1][1]
    assert "UPDATE verification_marker;" in events[1][1]


def test_canonical_persistence_failure_stops_before_next_row(monkeypatch, tmp_path):
    path = tmp_path / "result.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["restaurant_id", "komsco_name", "decision", "verification_reason"],
        )
        writer.writeheader()
        writer.writerow({
            "restaurant_id": "1",
            "komsco_name": "첫번째",
            "decision": "REJECT",
            "verification_reason": "NO_MATCH",
        })
        writer.writerow({
            "restaurant_id": "2",
            "komsco_name": "두번째",
            "decision": "REJECT",
            "verification_reason": "NO_MATCH",
        })

    executed = []

    def fail_once(*_args):
        executed.append("first")
        raise RuntimeError("transaction failed")

    monkeypatch.setattr(canonical_persistence_cli, "_execute_sql", fail_once)
    monkeypatch.setattr(
        PlaceDetailPersistence,
        "verification_sql",
        lambda *_, **__: "UPDATE verification_marker;",
    )

    with pytest.raises(RuntimeError, match="Failed to persist canonical/verification"):
        canonical_persistence_cli.process_csv(path, tmp_path)
    assert executed == ["first"]
