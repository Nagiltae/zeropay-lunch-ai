import argparse
import sys
import os
import subprocess
from pathlib import Path
import csv
import time

def _run_cmd(cmd: list[str]) -> bool:
    print(f"\n[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="End-to-End Orchestrator")
    parser.add_argument("--limit", type=int, default=10, help="Pilot size")
    args = parser.parse_args()
    
    root = Path(__file__).resolve().parent.parent.parent
    ai_dir = root / "ai"
    
    manifest_path = ai_dir / "build/reports/naver-place-pipeline/pilot.manifest"
    csv_path = ai_dir / "build/reports/naver-place-pipeline/pilot.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("\n=============================================")
    print(f"Step 1: KOMSCO Active Population Fetch (Limit: {args.limit})")
    print("=============================================")
    
    start_time = time.time()
    
    fetch_sql = f"""
    SELECT r.id as restaurant_id, r.external_merchant_id, r.name, r.address, r.latitude, r.longitude
    FROM restaurants r
    LEFT JOIN restaurant_naver_verifications v ON r.id = v.restaurant_id
    WHERE r.active = 1 
      AND v.restaurant_id IS NULL
    LIMIT {args.limit};
    """
    cmd = [
        "docker", "compose", "exec", "-T", "mysql", "sh", "-c",
        f'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 --batch -u zeropay zeropay_lunch -e "{fetch_sql}"'
    ]
    process = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    
    rows = process.stdout.strip().split('\n')
    target_count = len(rows) - 1 if len(rows) > 1 else 0
    if target_count == 0:
        print("No new active restaurants found. DB cache skipped all.")
        sys.exit(0)
        
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["external_merchant_id", "restaurant_id", "komsco_name", "komsco_address", "komsco_lat", "komsco_lon", "legal_dong_name"])
        for row in rows[1:]:
            cols = row.split('\t')
            # id, external_merchant_id, name, address, lat, lon
            writer.writerow([cols[1], cols[0], cols[2], cols[3], cols[4], cols[5], "논현동"])
            
    print(f"-> Selected {target_count} targets (Cache skipped previously verified ones).")
    
    print("\n=============================================")
    print("Step 2: Provider Fusion & Qwen Entity Resolution")
    print("=============================================")
    qwen_cmd = ["poetry", "run", "python", "-m", "app.provider_entity_resolution_cli", "--manifest", str(manifest_path), "--output", str(csv_path)]
    if not _run_cmd(qwen_cmd):
        print("Provider resolution failed.")
        sys.exit(1)
        
    # Analyze Qwen output
    accepts = rejects = unknowns = qwen_calls = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
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
        
    print("\n=============================================")
    print("Step 4: NAVER Place ID Linking (MATCHED only)")
    print("=============================================")
    linker_cmd = ["poetry", "run", "python", "-m", "app.place_id_linker_cli", "--limit", str(args.limit)]
    linker_result = subprocess.run(linker_cmd, capture_output=True, text=True)
    print(linker_result.stdout)
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
    print(f"- Qwen 호출 수 (Total Processed): {qwen_calls}")
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
