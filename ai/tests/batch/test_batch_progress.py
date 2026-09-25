"""배치 진행률·ETA·runtime report 형식을 검증한다. 외부 서비스는 호출하지 않는다."""

import json

import pytest

from app.batch.batch_progress import BatchProgress


def test_interval_summary_counts_eta_and_current_restaurant():
    output = []
    ticks = iter((0.0, 30.0, 60.0))
    progress = BatchProgress(
        "Entity Resolution", 4,
        {"cache_skip": "cache skip", "accept": "ACCEPT"},
        every=2, clock=lambda: next(ticks), emit=output.append,
    )
    progress.current(101, "첫 식당")
    progress.complete(cache_skip=1)
    assert len(output) == 1
    progress.current(102, "둘째 식당")
    progress.complete(accept=1)
    assert "2/4 (50.0%)" in output[-1]
    assert "cache skip: 1" in output[-1]
    assert "ACCEPT: 1" in output[-1]
    assert "elapsed: 30s" in output[-1]
    assert "avg: 15.0s/item" in output[-1]
    assert "ETA: 30s" in output[-1]
    progress.complete(accept=1)
    progress.complete(accept=1)
    assert "4/4 (100.0%)" in output[-1]
    assert "ETA: 0s" in output[-1]


def test_final_partial_interval_and_immediate_error():
    output = []
    progress = BatchProgress("Place ID", 3, {"matched": "MATCHED"},
                             every=10, clock=lambda: 0.0, emit=output.append)
    progress.error(429, "HTTP 429")
    assert output == ["[Place ID][ERROR] id=429 HTTP 429"]
    for _ in range(3):
        progress.complete(matched=1)
    assert "3/3 (100.0%)" in output[-1]
    assert "MATCHED: 3" in output[-1]


def test_default_ten_item_summary_can_be_configured(monkeypatch):
    output = []
    progress = BatchProgress("Detail", 11, {"success": "success"},
                             clock=lambda: 0.0, emit=output.append)
    for _ in range(9):
        progress.complete(success=1)
    assert output == []
    progress.complete(success=1)
    assert "10/11" in output[-1]
    progress.complete(success=1)
    assert "11/11" in output[-1]

    monkeypatch.setenv("BATCH_PROGRESS_EVERY", "25")
    configured = BatchProgress("Detail", 30, {"success": "success"},
                               clock=lambda: 0.0, emit=output.append)
    assert configured.every == 25


def test_block_report_keeps_last_success_and_enforces_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVER_BLOCK_COOLDOWN_SECONDS", "1800")
    progress = BatchProgress("Detail", 3, {"success": "success"}, report_dir=tmp_path,
                             run_id="unit-test", emit=lambda _: None)
    progress.current(101, "done")
    progress.record("success", 101, success=1)
    progress.current(102, "blocked")
    progress.block(102, RuntimeError("BLOCKED: HTTP 429"))
    report_path = progress.finish("BLOCKED", "BLOCKED: HTTP 429")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert (report["processed"], report["success"], report["failed"]) == (2, 1, 1)
    assert (report["http_429"], report["blocked"], report["retry"]) == (1, 1, 0)
    assert report["last_success_restaurant_id"] == 101
    assert report["last_failure_restaurant_id"] == 102
    assert report["resume_not_before"]
    with pytest.raises(RuntimeError, match="cooldown until"):
        BatchProgress.enforce_cooldown(tmp_path, "Detail")


def test_retry_count_and_interrupted_report(tmp_path):
    progress = BatchProgress("Place ID", 2, {}, report_dir=tmp_path,
                             run_id="interrupted", emit=lambda _: None)
    progress.retry(201, 0.0, TimeoutError("temporary timeout"))
    progress.current(201, "restaurant")
    progress.record("failed", 201)
    report = json.loads(progress.finish("INTERRUPTED", "KeyboardInterrupt").read_text())
    assert report["retry"] == 1
    assert report["status"] == "INTERRUPTED"
    assert report["resume_not_before"] is None


def test_runtime_report_records_playwright_lifecycle(tmp_path):
    progress = BatchProgress("Detail", 1, {}, report_dir=tmp_path,
                             run_id="playwright-lifecycle", emit=lambda _: None)
    progress.record_browser_lifecycle(browser_starts=1, page_recreates=2)
    progress.record_browser_lifecycle(browser_starts=1, browser_restarts=1)
    report = json.loads(progress.finish().read_text())
    assert report["browser_starts"] == 2
    assert report["browser_restarts"] == 1
    assert report["page_recreates"] == 2


def test_runtime_report_counts_business_hours_section_result(tmp_path):
    progress = BatchProgress("Detail", 1, {}, report_dir=tmp_path,
                             run_id="hours-metric", emit=lambda _: None)
    progress.record_detail_section_result("business_hours", "SUCCESS", reconciled=True)
    report = json.loads(progress.finish().read_text())
    assert report["hours_collected"] == 1
    assert report["section_reconciled"] == 1


def test_runtime_report_records_qwen_and_candidate_metrics(tmp_path):
    progress = BatchProgress("Entity Resolution", 1, {}, report_dir=tmp_path,
                             run_id="qwen-metrics", emit=lambda _: None)
    progress.record_qwen_call("choose", 1.0)
    progress.record_qwen_call("validate", 2.0)
    progress.record_qwen_call("validate_many", 3.0)
    progress.record_qwen_retry("validate_many")
    progress.record_validate_many(success=True, fallback=False)
    progress.record_validate_many(success=False, fallback=True)
    progress.record_qwen_candidate_count(1)
    progress.record_provider(kakao_requests=1, naver_requests=1, latency_seconds=0.1)
    progress.record_provider(
        kakao_requests=1, naver_requests=1, latency_seconds=0.1, round_number=2
    )
    progress.record_round1_resolved()
    progress.record_round2_required()
    progress.record_qwen_candidates(4, 3, 1)
    report = json.loads(progress.finish().read_text())
    assert report["qwen_calls"] == 3
    assert report["qwen_choose_calls"] == 1
    assert report["qwen_validate_calls"] == 1
    assert report["qwen_validate_many_calls"] == 1
    assert report["validate_many_success"] == 1
    assert report["validate_many_fallback"] == 1
    assert report["single_candidate_choose_skipped"] == 1
    assert report["qwen_candidate_count_sent"] == 1
    assert report["structured_output_retries"] == 1
    assert report["semantic_contract_retries"] == 1
    assert report["round1_requests"] == 2
    assert report["round2_requests"] == 2
    assert report["round1_resolved"] == 1
    assert report["round2_required"] == 1
    assert report["qwen_total_latency_seconds"] == 6.0
    assert report["qwen_avg_latency_seconds"] == 2.0
    assert report["candidate_count_before_dedup"] == 4
    assert report["candidate_count_after_dedup"] == 3
    assert report["duplicate_candidates_removed"] == 1


def test_runtime_report_records_place_id_evidence_metrics(tmp_path):
    progress = BatchProgress("Place ID", 2, {"matched": "MATCHED"}, report_dir=tmp_path)
    progress.record_place_id_observation(
        local_evidence=True,
        raw_candidates=3,
        numeric_candidates=2,
        rejected_candidates=1,
    )
    progress.record_place_id_observation(
        local_evidence=False,
        raw_candidates=1,
        numeric_candidates=1,
        rejected_candidates=1,
    )
    report = json.loads(progress.finish().read_text())
    assert report["place_id_queries"] == 2
    assert report["place_id_local_evidence"] == 1
    assert report["place_id_canonical_fallback"] == 1
    assert report["place_id_raw_candidates"] == 4
    assert report["place_id_numeric_candidates"] == 3
    assert report["place_id_rejected_candidates"] == 2
