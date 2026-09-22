"""KOMSCO 원천부터 상세 수집까지의 증분 배치를 단계별 CLI로 연결한다.

이 모듈은 의미 판단이나 DB 세부 SQL을 소유하지 않고 각 단계의 성공 여부와
DB 기반 resume 조건을 확인한다.  한 단계가 실패하면 뒤 단계는 실행하지 않는다.
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.batch.batch_progress import BatchProgress
from app.entity_resolution.provider_entity_resolution_cli import _source
from app.entity_resolution.verification_quality_gate import source_fingerprint
from app.naver.place_resolver import RestaurantReference


def _pending(row: dict[str, str]) -> bool:
    """KOMSCO 매칭 입력이 같고 VERIFIED인 경우에만 이전 검증을 재사용한다."""

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
    return row["verification_status"] != "VERIFIED" or row[
        "source_fingerprint"
    ] != source_fingerprint(_source(reference))


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
        return "RETRY_UNKNOWN"
    if status == "REJECTED":
        return "REJECT_CACHE_CANDIDATE"
    return "VERIFICATION_PENDING"


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
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            if on_line is not None:
                on_line(line)
        return process.wait() == 0


def main():
    parser = argparse.ArgumentParser(description="End-to-End Orchestrator")
    parser.add_argument("--limit", type=int, default=10, help="Pilot size")
    parser.add_argument(
        "--restaurant-ids", help="Comma-separated restaurant IDs for a bounded audit"
    )
    parser.add_argument("--verification-only", action="store_true")
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

    root = Path(__file__).resolve().parent.parent.parent
    ai_dir = root / "ai"

    run_dir = ai_dir / "build/reports/naver-place-pipeline/e2e"
    run_name = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
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
           r.latitude, r.longitude, v.verification_status, v.source_fingerprint
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
    pending_rows = [row for row in source_rows if _pending(row)]
    for row in pending_rows:
        row["processing_reason"] = _verification_work_reason(row)
    verified_skipped = len(source_rows) - len(pending_rows)
    verification_reasons = Counter(
        row.get("processing_reason", "VERIFICATION_PENDING") for row in pending_rows
    )
    rows = pending_rows[: args.limit]
    print(
        f"DB verification: population={len(source_rows)}, verified skip={verified_skipped}, "
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
            str(verified_skipped),
        ]
        if not _run_cmd(qwen_cmd, cwd=ai_dir):
            print("Provider resolution failed.")
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
        skipped_progress.finish()
    if args.verification_only:
        print(
            "Verification complete: "
            f"targets={target_count}, qwen={qwen_calls}, "
            f"cache_skips={cache_skips}, accepts={accepts}, "
            f"rejects={rejects}, unknowns={unknowns}"
        )
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
        sys.exit(1)

    elapsed = time.time() - start_time
    avg_time = elapsed / target_count if target_count > 0 else 0

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
