"""E2E 오케스트레이터의 상태 판정과 child CLI 실행 경로를 검증한다."""

import subprocess
import sys
from datetime import UTC, datetime, timedelta

from app.batch.e2e_pipeline_orchestrator import (
    _pending,
    _project_paths,
    _verification_work_reason,
)
from app.entity_resolution.provider_entity_resolution_cli import SEARCH_POLICY_VERSION, _source
from app.entity_resolution.verification_quality_gate import source_fingerprint
from app.naver.place_resolver import RestaurantReference


def test_child_cli_paths_use_repository_ai_directory():
    repository_root, ai_dir = _project_paths()
    assert ai_dir == repository_root / "ai"
    assert (ai_dir / "app").is_dir()
    report_dir = ai_dir / "build/reports/naver-place-pipeline/e2e"
    assert report_dir.parent.parent.parent == ai_dir / "build"

    # 실제 subprocess cwd에서 모든 E2E child module의 import/argparse 경계를 확인한다.
    modules = (
        "app.entity_resolution.provider_entity_resolution_cli",
        "app.canonical.canonical_persistence_cli",
        "app.naver.place_id_linker_cli",
        "app.naver.place_detail_enrichment_cli",
    )
    for module in modules:
        result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=ai_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


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
    assert not _pending({**row, "verification_status": "REJECTED"})


def test_legacy_reject_requires_explicit_revalidation_only():
    row = {
        "restaurant_id": "9560",
        "external_merchant_id": "merchant-9560",
        "name": "원래 음식점",
        "address": "서울 강남구 논현동 1",
        "latitude": "37.51",
        "longitude": "127.02",
        "verification_status": "REJECTED",
        "source_fingerprint": "",
        "search_policy_version": "",
    }
    reference = RestaurantReference(
        9560, row["name"], row["address"], 37.51, 127.02,
        "논현동", row["external_merchant_id"],
    )
    row["source_fingerprint"] = source_fingerprint(_source(reference))
    assert not _pending(row)
    assert _pending(row, revalidate_rejected=True)
    assert not _pending(
        {**row, "search_policy_version": SEARCH_POLICY_VERSION},
        revalidate_rejected=True,
    )


def test_unknown_same_fingerprint_waits_for_reason_ttl():
    now = datetime.now(UTC)
    row = {
        "restaurant_id": "9560",
        "external_merchant_id": "merchant-9560",
        "name": "원래 음식점",
        "address": "서울 강남구 논현동 1",
        "latitude": "37.51",
        "longitude": "127.02",
        "verification_status": "ERROR",
        "verification_reason": "QWEN_TIMEOUT",
        "last_attempt_at": now.isoformat(),
        "source_fingerprint": "",
    }
    reference = RestaurantReference(
        9560, row["name"], row["address"], 37.51, 127.02,
        "논현동", row["external_merchant_id"],
    )
    row["source_fingerprint"] = source_fingerprint(_source(reference))
    assert not _pending(row)
    assert _verification_work_reason(row) == "TTL_NOT_EXPIRED"
    assert _pending({**row, "last_attempt_at": (now - timedelta(minutes=10)).isoformat()})
    assert _pending({**row, "name": "변경 음식점"})
