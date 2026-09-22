"""E2E 오케스트레이터의 fingerprint 기반 pending 판정을 검증한다."""

from app.batch.e2e_pipeline_orchestrator import _pending
from app.entity_resolution.provider_entity_resolution_cli import _source
from app.entity_resolution.verification_quality_gate import source_fingerprint
from app.naver.place_resolver import RestaurantReference


def test_verified_fingerprint_skips_and_source_change_rechecks():
    row = {
        "restaurant_id": "9560",
        "external_merchant_id": "merchant-9560",
        "name": "원래 음식점",
        "address": "서울 강남구 논현동 1",
        "latitude": "37.51",
        "longitude": "127.02",
        "verification_status": "VERIFIED",
        "source_fingerprint": "",
    }
    reference = RestaurantReference(
        9560, row["name"], row["address"], 37.51, 127.02,
        "논현동", row["external_merchant_id"],
    )
    row["source_fingerprint"] = source_fingerprint(_source(reference))
    assert not _pending(row)
    assert _pending({**row, "name": "변경 음식점"})
    assert _pending({**row, "source_fingerprint": "NULL"})
    assert _pending({**row, "verification_status": "REJECTED"})
