import argparse
import sys
import os
import subprocess
from pathlib import Path
import csv
import time
from datetime import datetime

from app.place_resolver import RestaurantReference
from app.provider_entity_resolution_cli import _source
from app.verification_quality_gate import source_fingerprint


def _pending(row: dict[str, str]) -> bool:
    """A verified row is durable only while its KOMSCO matching fields agree."""
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
    return (
        row["verification_status"] != "VERIFIED"
        or row["source_fingerprint"] != source_fingerprint(_source(reference))
    )

def _run_cmd(cmd: list[str]) -> bool:
    print(f"\n[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="End-to-End Orchestrator")
    parser.add_argument("--limit", type=int, default=10, help="Pilot size")
    parser.add_argument("--restaurant-ids", help="Comma-separated restaurant IDs for a bounded audit")
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
    manifest_path = run_dir / f"{run_name}.manifest"
    csv_path = run_dir / f"{run_name}.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("\n=============================================")
    print(f"Step 1: KOMSCO Active Population Fetch (Limit: {args.limit})")
    print("=============================================")
    
    start_time = time.time()
    
    requested_filter = (
        f"AND r.id IN ({','.join(str(value) for value in requested_ids)})"
        if requested_ids else ""
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
        "docker", "compose", "exec", "-T", "mysql", "sh", "-c",
        f'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 --batch -u zeropay zeropay_lunch -e "{fetch_sql}"'
    ]
    process = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    if process.returncode != 0:
        raise RuntimeError(f"KOMSCO selection query failed: {process.stderr}")
    
    lines = process.stdout.strip().splitlines()
    headers = lines[0].split('\t') if lines else []
    source_rows = [dict(zip(headers, line.split('\t'))) for line in lines[1:]]
    rows = [row for row in source_rows if _pending(row)][:args.limit]
    target_count = len(rows)
    accepts = rejects = unknowns = qwen_calls = cache_skips = 0
    if target_count:
        with open(manifest_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["external_merchant_id", "restaurant_id", "komsco_name", "komsco_address", "komsco_lat", "komsco_lon", "legal_dong_name"])
            for row in rows:
                writer.writerow([
                    row["external_merchant_id"], row["restaurant_id"], row["name"],
                    row["address"], row["latitude"], row["longitude"], "논현동",
                ])

        print(f"-> Selected {target_count} targets (Cache skipped previously verified ones).")
        print("\n=============================================")
        print("Step 2: Provider Fusion & Qwen Entity Resolution")
        print("=============================================")
        qwen_cmd = ["poetry", "run", "python", "-m", "app.provider_entity_resolution_cli", "--manifest", str(manifest_path), "--output", str(csv_path), "--db-reject-cache"]
        if not _run_cmd(qwen_cmd):
            print("Provider resolution failed.")
            sys.exit(1)

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("qwen_calls_skipped") == "true":
                    cache_skips += 1
                else:
                    qwen_calls += 1
                if row.get("decision") == "ACCEPT": accepts += 1
                elif row.get("decision") == "REJECT": rejects += 1
                else: unknowns += 1

        print("\n=============================================")
        print("Step 3: Canonical Persistence (ACCEPT only)")
        print("=============================================")
        canonical_cmd = ["poetry", "run", "python", "-m", "app.canonical_persistence_cli", "--csv", str(csv_path)]
        if not _run_cmd(canonical_cmd):
            print("Canonical persistence failed.")
            sys.exit(1)
    else:
        print("No verification work; continuing to incomplete Place ID/detail stages.")
    if args.verification_only:
        print(f"Verification complete: targets={target_count}, qwen={qwen_calls}, cache_skips={cache_skips}, accepts={accepts}, rejects={rejects}, unknowns={unknowns}")
        return
        
    print("\n=============================================")
    print("Step 4: NAVER Place ID Linking (MATCHED only)")
    print("=============================================")
    linker_cmd = ["poetry", "run", "python", "-m", "app.place_id_linker_cli", "--limit", str(args.limit)]
    if requested_ids:
        linker_cmd.extend(["--restaurant-ids", ",".join(map(str, requested_ids))])
    linker_result = subprocess.run(linker_cmd, capture_output=True, text=True)
    print(linker_result.stdout)
    if linker_result.stderr:
        print(linker_result.stderr, file=sys.stderr)
    if linker_result.returncode != 0:
        print("Place ID linking failed.")
        sys.exit(1)
        
    matched = linker_result.stdout.count("Status: MATCHED")
    ambiguous = linker_result.stdout.count("Status: AMBIGUOUS")
    unresolved = linker_result.stdout.count("Status: UNRESOLVED")
        
    print("\n=============================================")
    print("Step 5: Detail Enrichment (Numeric Place ID only)")
    print("=============================================")
    detail_cmd = ["poetry", "run", "python", "-m", "app.place_detail_enrichment_cli", "--limit", str(args.limit)]
    if requested_ids:
        detail_cmd.extend(["--restaurant-ids", ",".join(map(str, requested_ids))])
    detail_result = subprocess.run(detail_cmd, capture_output=True, text=True)
    print(detail_result.stdout)
    if detail_result.returncode != 0:
        print("Detail enrichment failed.")
        sys.exit(1)
        
    detail_success = detail_result.stdout.count("Successfully persisted details to DB")
    detail_skip = detail_result.stdout.count("Skipping persistence to protect existing data")
    
    elapsed = time.time() - start_time
    avg_time = elapsed / target_count if target_count > 0 else 0
    
    print("\n=============================================")
    print("Pipeline Execution Completed.")
    print("=============================================")
    print("[Pilot Report]")
    print(f"- 총 대상 (Target): {target_count}")
    print(f"- Cache Skip (DB Verifications): DB 레벨에서 기 처리 건 제외됨")
    print(f"- 실제 Qwen 호출 수: {qwen_calls}")
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
