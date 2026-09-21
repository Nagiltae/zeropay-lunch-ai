from app import place_pipeline_cli as pipeline

from app.place_resolver import ResolutionStatus, RestaurantReference
from app.place_request_limiter import NavigationRateLimiter
import csv


def test_blocked_stops_before_next_restaurant_handler():
    called = []

    def handler(item):
        called.append(item)
        if item == 2:
            raise RuntimeError("BLOCKED: HTTP 429")
        return item

    results, blocked = pipeline.run_until_blocked([1, 2, 3], handler)

    assert results == [1]
    assert blocked is True
    assert called == [1, 2]


def test_verified_checkpoint_reuses_place_id_without_resolution():
    reference = RestaurantReference(
        restaurant_id=4280,
        komsco_name="소나무",
        komsco_address="서울 강남구 압구정로28길 22-9",
        komsco_latitude=None,
        komsco_longitude=None,
        legal_dong="신사동",
    )
    result = pipeline.checkpoint_result(reference, {
        "place_id": "1618902912",
        "resolved_name": "소나무소고기구이",
        "resolved_address": "서울 강남구 압구정로28길 22-9 1층",
    })

    assert result.matcher_source == "VERIFIED_CHECKPOINT"
    assert result.place_id == "1618902912"
    assert result.resolution.status is ResolutionStatus.RESOLVED


def test_default_checkpoint_is_komsco_only():
    assert pipeline.DEFAULT_CHECKPOINT_NAME == "verified-place-ids-komsco-only.csv"


def test_navigation_rate_limiter_is_injectable_and_paces_calls():
    now = [0.0]
    sleeps = []

    limiter = NavigationRateLimiter(
        navigation_delay=3.0,
        restaurant_delay=5.0,
        clock=lambda: now[0],
        sleeper=lambda value: sleeps.append(value),
    )
    limiter.before_navigation()
    now[0] = 1.0
    limiter.before_navigation()
    limiter.after_restaurant()

    assert sleeps == [2.0, 5.0]


def test_pipeline_limit_stops_at_exactly_ten_items():
    class Item:
        def __init__(self, restaurant_id):
            self.restaurant_id = restaurant_id

    selected = pipeline.select_pipeline_references(
        [Item(index) for index in range(25)], limit=10
    )
    calls = []
    for item in selected:
        calls.append(item.restaurant_id)

    assert calls == list(range(10))
    assert len(calls) == 10


def test_manual_review_sidecar_preserves_category_coordinates_and_attempts(tmp_path):
    report = tmp_path / "report.csv"
    with report.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=pipeline.FIELDS)
        writer.writeheader()
        row = {field: "" for field in pipeline.FIELDS}
        row.update({
            "restaurant_id": "1", "external_merchant_id": "stable-1",
            "komsco_name": "테스트", "komsco_address": "주소",
            "resolve_status": "RESOLVED", "verification_status": "VERIFIED",
            "verification_reason": "MATCHED", "place_id": "99", "elapsed_ms": "10",
            "qwen_ranking": "0", "candidate_attempts_json": '[{"rank":1,"place_id":"99",'
            '"candidate_name":"테스트","category_values":["음식점","한식"],'
            '"candidate_jibun_address":"서울 논현동 1","candidate_road_address":"논현로 1",'
            '"candidate_longitude":127.0,"candidate_latitude":37.5,"final_decision":"ACCEPT"}]',
        })
        writer.writerow(row)
    sidecar = pipeline.write_manual_review_csv(report)
    review = list(csv.DictReader(sidecar.open(encoding="utf-8")))[0]
    assert review["external_merchant_id"] == "stable-1"
    assert review["selected_category_values"] == '["음식점", "한식"]'
    assert review["selected_x"] == "127.0"
    assert review["selected_y"] == "37.5"
    assert review["gold_label"] == ""


def test_pipeline_accepts_explicit_multi_id_batch():
    class Item:
        def __init__(self, restaurant_id):
            self.restaurant_id = restaurant_id

    selected = pipeline.select_pipeline_references(
        [Item(index) for index in range(20)], restaurant_id=[3, 7, 11]
    )
    assert [item.restaurant_id for item in selected] == [3, 7, 11]


def test_persistence_connection_failure_is_batch_fatal_but_data_error_is_not():
    assert pipeline.is_fatal_persistence_error(RuntimeError("detail persistence failed: connection refused"))
    assert pipeline.is_fatal_persistence_error(RuntimeError("detail persistence failed: duplicate value")) is False


def test_manifest_and_terminal_ledger_resume_atomic(tmp_path):
    manifest = tmp_path / "batch.manifest"
    manifest.write_text("1\n2\n3\n", encoding="utf-8")
    assert pipeline.load_batch_manifest(manifest) == [1, 2, 3]
    ledger_path = tmp_path / "batch.ledger.csv"
    ledger = pipeline.ResumeLedger(ledger_path, resume=False)
    ledger.record(1, "AMBIGUOUS", reason="TOP_K_DETAIL_VALIDATION_FAILED")
    ledger.record(2, "ERROR", reason="LOCATOR_TIMEOUT")
    resumed = pipeline.ResumeLedger(ledger_path, resume=True)
    assert resumed.completed_ids() == {1}
    assert resumed.completed_ids(retry_failed=True) == {1}
    assert "2,ERROR" in ledger_path.read_text(encoding="utf-8")


def test_manifest_rejects_duplicate_ids(tmp_path):
    manifest = tmp_path / "duplicate.manifest"
    manifest.write_text("1\n1\n", encoding="utf-8")
    try:
        pipeline.load_batch_manifest(manifest)
    except RuntimeError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate manifest ids must be rejected")


def test_stable_manifest_reads_external_merchant_identity(tmp_path):
    manifest = tmp_path / "stable.manifest"
    manifest.write_text(
        "# stable KOMSCO sample\nexternal_merchant_id,restaurant_id\nmerchant-a,10\nmerchant-b,11\n",
        encoding="utf-8",
    )
    ids, rows = pipeline.load_manifest(manifest)
    assert ids is None
    assert [row["external_merchant_id"] for row in rows] == ["merchant-a", "merchant-b"]
