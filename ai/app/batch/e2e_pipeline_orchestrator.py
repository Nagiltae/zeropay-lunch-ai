"""KOMSCO 원천부터 상세 수집까지의 증분 배치를 단계별 CLI로 연결한다.

이 모듈은 의미 판단이나 DB 세부 SQL을 소유하지 않고 각 단계의 성공 여부와
DB 기반 resume 조건을 확인한다.  한 단계가 실패하면 뒤 단계는 실행하지 않는다.
"""

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.batch.batch_progress import BatchProgress
from app.entity_resolution.provider_entity_resolution_cli import SEARCH_POLICY_VERSION, _source
from app.entity_resolution.verification_quality_gate import source_fingerprint, unknown_reason_kind
from app.naver.place_resolver import RestaurantReference


def _retry_ttl_seconds(reason: str) -> float:
    defaults = {"TECHNICAL": 300.0, "RETRIEVAL": 3600.0, "SEMANTIC": 86400.0}
    kind = unknown_reason_kind(reason)
    env_name = {
        "TECHNICAL": "BATCH_UNKNOWN_TECHNICAL_RETRY_TTL_SECONDS",
        "RETRIEVAL": "BATCH_UNKNOWN_NO_CANDIDATE_RETRY_TTL_SECONDS",
        "SEMANTIC": "BATCH_UNKNOWN_SEMANTIC_RETRY_TTL_SECONDS",
    }.get(kind)
    return (
        max(0.0, float(os.environ.get(env_name, defaults.get(kind, 3600.0))))
        if env_name else 0.0
    )


def _retry_ttl_expired(row: dict[str, str], now: datetime | None = None) -> bool:
    if row.get("verification_status") not in {"ERROR", "UNKNOWN"}:
        return True
    attempt = row.get("last_attempt_at", "")
    if not attempt or attempt in {"NULL", "None"}:
        return True
    try:
        attempted_at = datetime.fromisoformat(attempt.replace("Z", "+00:00"))
    except ValueError:
        return True
    now = now or datetime.now(UTC)
    if attempted_at.tzinfo is None:
        attempted_at = attempted_at.replace(tzinfo=now.tzinfo)
    return now - attempted_at >= timedelta(
        seconds=_retry_ttl_seconds(row.get("verification_reason", ""))
    )


def _pending(row: dict[str, str], *, revalidate_rejected: bool = False) -> bool:
    """동일 fingerprint의 확정 VERIFIED/REJECTED 결과는 앞단에서 재사용한다."""

    def coordinate(value: str) -> float | None:
        return None if value in ("", "NULL") else float(value)

    reference = RestaurantReference(
        restaurant_id=int(row["restaurant_id"]),
        external_merchant_id=row["external_merchant_id"],
        komsco_name=row["name"],
        komsco_address=row["address"],
        komsco_latitude=coordinate(row["latitude"]),
        komsco_longitude=coordinate(row["longitude"]),
        legal_dong="논현동",
    )
    same_source = row["source_fingerprint"] == source_fingerprint(_source(reference))
    if not same_source:
        return True
    if row["verification_status"] in {"VERIFIED", "REJECTED"}:
        if (
            revalidate_rejected
            and row["verification_status"] == "REJECTED"
            and row.get("search_policy_version") not in {SEARCH_POLICY_VERSION}
        ):
            return True
        return False
    if row["verification_status"] in {"ERROR", "UNKNOWN"}:
        return _retry_ttl_expired(row)
    return True


def _verification_work_reason(row: dict[str, str]) -> str:
    # DB 상태를 새 enum으로 늘리지 않고, 이번 실행에서 왜 재검증하는지만 런타임 보고에 남긴다.
    status = row.get("verification_status", "")
    stored_fingerprint = row.get("source_fingerprint", "")
    if not status or status == "NULL":
        return "NEW_SOURCE"
    reference = RestaurantReference(
        restaurant_id=int(row["restaurant_id"]),
        external_merchant_id=row["external_merchant_id"],
        komsco_name=row["name"],
        komsco_address=row["address"],
        komsco_latitude=None if row["latitude"] in ("", "NULL") else float(row["latitude"]),
        komsco_longitude=None if row["longitude"] in ("", "NULL") else float(row["longitude"]),
        legal_dong="논현동",
    )
    if stored_fingerprint != source_fingerprint(_source(reference)):
        return "SOURCE_CHANGED"
    if status in {"ERROR", "UNKNOWN"}:
        return "RETRY_UNKNOWN" if _retry_ttl_expired(row) else "TTL_NOT_EXPIRED"
    if status == "REJECTED":
        return "REJECT_CACHE_CANDIDATE"
    return "VERIFICATION_PENDING"


def _write_e2e_summary(
    run_dir: Path,
    run_id: str,
    started_at: datetime,
    *,
    status: str,
    failed_stage: str | None = None,
    reason: str | None = None,
) -> None:
    stage_reports = {}
    for path in sorted(run_dir.glob(f"{run_id}-*.json")):
        if path.name.endswith("-summary.json"):
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            stage_reports[report.get("stage", path.stem)] = {
                key: report.get(key)
                for key in (
                    "status", "target_count", "processed", "success", "failed",
                    "skipped", "retry", "blocked", "last_success_restaurant_id",
                    "last_failure_restaurant_id", "interruption_reason",
                )
            }
        except (OSError, ValueError):
            continue
    summary = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "status": status,
        "failed_stage": failed_stage,
        "interruption_reason": reason,
        "stage_reports": stage_reports,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / f"{run_id}-summary.json").open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _run_cmd(cmd: list[str], *, cwd: Path | None = None, on_line=None) -> bool:
    """Forward child output as it arrives while retaining lightweight counters."""
    print(f"\n[RUN] {' '.join(cmd)}", flush=True)
    environment = {**os.environ, "PYTHONUNBUFFERED": "1"}
    with subprocess.Popen(
        cmd,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    ) as process:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                if on_line is not None:
                    on_line(line)
            return process.wait() == 0
        except KeyboardInterrupt:
            # 부모가 먼저 중단되어도 외부 호출 child를 남기지 않고 종료한다.
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
            raise


def _project_paths() -> tuple[Path, Path]:
    """Return the repository root and the real ``ai`` working directory."""
    ai_dir = Path(__file__).resolve().parents[2]
    return ai_dir.parent, ai_dir


def main():
    parser = argparse.ArgumentParser(description="End-to-End Orchestrator")
    parser.add_argument("--limit", type=int, default=10, help="Pilot size")
    parser.add_argument(
        "--restaurant-ids", help="Comma-separated restaurant IDs for a bounded audit"
    )
    parser.add_argument("--verification-only", action="store_true")
    parser.add_argument(
        "--revalidate-rejected",
        action="store_true",
        help="explicitly recheck legacy or outdated REJECT rows without bulk invalidation",
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    requested_ids = None
    if args.restaurant_ids:
        try:
            requested_ids = [int(value) for value in args.restaurant_ids.split(",")]
        except ValueError:
            parser.error("--restaurant-ids must contain only integers")
        if not requested_ids or any(value < 1 for value in requested_ids):
            parser.error("--restaurant-ids must contain positive integers")
        if len(requested_ids) > args.limit:
            parser.error("--restaurant-ids exceeds --limit")

    root, ai_dir = _project_paths()

    run_dir = ai_dir / "build/reports/naver-place-pipeline/e2e"
    run_name = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_started_at = datetime.now(UTC)
    os.environ["BATCH_RUN_ID"] = run_name
    print(f"[Batch] run_id={run_name} stage reports={run_dir}", flush=True)
    manifest_path = run_dir / f"{run_name}.manifest"
    csv_path = run_dir / f"{run_name}.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    print("\n=============================================")
    print(f"Step 1: KOMSCO Active Population Fetch (Limit: {args.limit})")
    print("=============================================")

    start_time = time.time()

    requested_filter = (
        f"AND r.id IN ({','.join(str(value) for value in requested_ids)})" if requested_ids else ""
    )
    fetch_sql = f"""
    SELECT r.id as restaurant_id, r.external_merchant_id, r.name, r.address,
           r.latitude, r.longitude, v.verification_status, v.source_fingerprint,
           v.verification_reason, v.last_attempt_at, v.search_policy_version
    FROM restaurants r
    LEFT JOIN restaurant_naver_verifications v
      ON r.id = v.restaurant_id AND v.provider = 'NAVER'
    WHERE r.active = 1 AND r.source_provider = 'KOMSCO'
      AND r.legal_dong_code = '11680108'
      AND r.provider_institution_code = 'I0000002'
      AND r.industry_code = '561'
      AND r.business_status_name = '계속사업자'
      {requested_filter}
    ORDER BY v.source_fingerprint IS NOT NULL, r.id;
    """
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        f'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 '
        f'--batch -u zeropay zeropay_lunch -e "{fetch_sql}"',
    ]
    process = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    if process.returncode != 0:
        raise RuntimeError(f"KOMSCO selection query failed: {process.stderr}")

    lines = process.stdout.strip().splitlines()
    headers = lines[0].split("\t") if lines else []
    source_rows = [dict(zip(headers, line.split("\t"), strict=True)) for line in lines[1:]]
    for row in source_rows:
        row["processing_reason"] = _verification_work_reason(row)
    pending_rows = [
        row for row in source_rows
        if _pending(row, revalidate_rejected=args.revalidate_rejected)
    ]
    preexisting_skipped = len(source_rows) - len(pending_rows)
    verified_skipped = sum(
        row.get("verification_status") == "VERIFIED"
        for row in source_rows
        if not _pending(row, revalidate_rejected=args.revalidate_rejected)
    )
    reject_cache_skipped = sum(
        row.get("verification_status") == "REJECTED"
        for row in source_rows
        if not _pending(row, revalidate_rejected=args.revalidate_rejected)
    )
    ttl_skipped = sum(
        row.get("processing_reason") == "TTL_NOT_EXPIRED"
        for row in source_rows
        if not _pending(row, revalidate_rejected=args.revalidate_rejected)
    )
    verification_reasons = Counter(
        row.get("processing_reason", "VERIFICATION_PENDING") for row in pending_rows
    )
    rows = pending_rows[: args.limit]
    print(
        f"DB verification: population={len(source_rows)}, verified skip={verified_skipped}, "
        f"reject cache skip={reject_cache_skipped}, "
        f"pending={len(pending_rows)}, selected={len(rows)}, "
        f"reasons={dict(verification_reasons)}",
        flush=True,
    )
    target_count = len(rows)
    accepts = rejects = unknowns = qwen_calls = cache_skips = 0
    if target_count:
        with open(manifest_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "external_merchant_id",
                    "restaurant_id",
                    "komsco_name",
                    "komsco_address",
                    "komsco_lat",
                    "komsco_lon",
                    "legal_dong_name",
                    "processing_reason",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["external_merchant_id"],
                        row["restaurant_id"],
                        row["name"],
                        row["address"],
                        row["latitude"],
                        row["longitude"],
                        "논현동",
                        row["processing_reason"],
                    ]
                )

        print(f"-> Selected {target_count} targets (Cache skipped previously verified ones).")
        print("\n=============================================")
        print("Step 2: Provider Fusion & Qwen Entity Resolution")
        print("=============================================")
        qwen_cmd = [
            "poetry",
            "run",
            "python",
            "-u",
            "-m",
            "app.entity_resolution.provider_entity_resolution_cli",
            "--manifest",
            str(manifest_path),
            "--output",
            str(csv_path),
            "--db-reject-cache",
            "--preexisting-skipped",
            str(preexisting_skipped),
        ]
        if args.revalidate_rejected:
            qwen_cmd.remove("--db-reject-cache")
        if not _run_cmd(qwen_cmd, cwd=ai_dir):
            print("Provider resolution failed.")
            _write_e2e_summary(run_dir, run_name, run_started_at,
                               status="FAILED", failed_stage="Entity Resolution")
            sys.exit(1)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("qwen_calls_skipped") == "true":
                    cache_skips += 1
                elif (
                    int(row.get("kakao_candidate_count") or 0)
                    + int(row.get("naver_candidate_count") or 0)
                    > 0
                ):
                    qwen_calls += 1
                if row.get("decision") == "ACCEPT":
                    accepts += 1
                elif row.get("decision") == "REJECT":
                    rejects += 1
                else:
                    unknowns += 1

        print("\n=============================================")
        print("Step 3: Canonical Persistence (ACCEPT only)")
        print("=============================================")
        canonical_cmd = [
            "poetry",
            "run",
            "python",
            "-u",
            "-m",
            "app.canonical.canonical_persistence_cli",
            "--csv",
            str(csv_path),
        ]
        if not _run_cmd(canonical_cmd, cwd=ai_dir):
            print("Canonical persistence failed.")
            _write_e2e_summary(run_dir, run_name, run_started_at,
                               status="FAILED", failed_stage="Canonical")
            sys.exit(1)
    else:
        print("No verification work; continuing to incomplete Place ID/detail stages.")
        skipped_progress = BatchProgress(
            "Entity Resolution",
            0,
            {},
            report_dir=run_dir,
            run_id=run_name,
        )
        skipped_progress.skip_preexisting(verified_skipped)
        skipped_progress.record_reason("UNCHANGED_VERIFIED", verified_skipped)
        skipped_progress.record_reason("TTL_NOT_EXPIRED", ttl_skipped)
        skipped_progress.finish()
    if args.verification_only:
        print(
            "Verification complete: "
            f"targets={target_count}, qwen={qwen_calls}, "
            f"cache_skips={cache_skips}, accepts={accepts}, "
            f"rejects={rejects}, unknowns={unknowns}"
        )
        _write_e2e_summary(run_dir, run_name, run_started_at, status="SUCCESS")
        return

    print("\n=============================================")
    print("Step 4: NAVER Place ID Linking (MATCHED only)")
    print("=============================================")
    linker_cmd = [
        "poetry",
        "run",
        "python",
        "-u",
        "-m",
        "app.naver.place_id_linker_cli",
        "--limit",
        str(args.limit),
    ]
    if requested_ids:
        linker_cmd.extend(["--restaurant-ids", ",".join(map(str, requested_ids))])
    matched = ambiguous = unresolved = 0

    def count_linker(line: str) -> None:
        nonlocal matched, ambiguous, unresolved
        if "Result:" not in line:
            return
        matched += int("Status: MATCHED" in line)
        ambiguous += int("Status: AMBIGUOUS" in line)
        unresolved += int("Status: UNRESOLVED" in line)

    if not _run_cmd(linker_cmd, cwd=ai_dir, on_line=count_linker):
        print("Place ID linking failed.")
        _write_e2e_summary(run_dir, run_name, run_started_at,
                           status="FAILED", failed_stage="Place ID")
        sys.exit(1)

    print("\n=============================================")
    print("Step 5: Detail Enrichment (Numeric Place ID only)")
    print("=============================================")
    detail_cmd = [
        "poetry",
        "run",
        "python",
        "-u",
        "-m",
        "app.naver.place_detail_enrichment_cli",
        "--limit",
        str(args.limit),
    ]
    if requested_ids:
        detail_cmd.extend(["--restaurant-ids", ",".join(map(str, requested_ids))])
    detail_success = detail_skip = 0

    def count_detail(line: str) -> None:
        nonlocal detail_success, detail_skip
        detail_success += int("Successfully persisted details to DB" in line)
        detail_skip += int(
            any(
                token in line
                for token in (
                    "Skipping persistence to protect existing data",
                    "Crawler threw exception",
                    "Persistence failed",
                    "Incomplete REVIEW, MENU/price or BUSINESS HOURS",
                )
            )
        )

    if not _run_cmd(detail_cmd, cwd=ai_dir, on_line=count_detail):
        print("Detail enrichment failed.")
        _write_e2e_summary(run_dir, run_name, run_started_at,
                           status="FAILED", failed_stage="Detail")
        sys.exit(1)

    elapsed = time.time() - start_time
    avg_time = elapsed / target_count if target_count > 0 else 0
    _write_e2e_summary(run_dir, run_name, run_started_at, status="SUCCESS")

    print("\n=============================================")
    print("Pipeline Execution Completed.")
    print("=============================================")
    print("[Pilot Report]")
    print(f"- 총 대상 (Target): {target_count}")
    print(f"- DB VERIFIED skip: {verified_skipped}")
    print(f"- Qwen 호출 음식점 수: {qwen_calls}")
    print(f"- Reject Cache skip: {cache_skips}")
    print(f"- ACCEPT: {accepts}")
    print(f"- REJECT: {rejects}")
    print(f"- UNKNOWN: {unknowns}")
    print(f"- Canonical 생성/갱신: {accepts}")
    print(f"- NAVER MATCHED (Linked): {matched}")
    print(f"- UNRESOLVED: {unresolved}")
    print(f"- AMBIGUOUS: {ambiguous}")
    print(f"- Detail 성공: {detail_success}")
    print(f"- Detail 부분 성공 / 실패 (Block/Timeout Skip): {detail_skip}")
    print(f"- 전체 실행시간: {elapsed:.2f}s")
    print(f"- restaurant당 평균시간: {avg_time:.2f}s")
    print("=============================================")


if __name__ == "__main__":
    main()
