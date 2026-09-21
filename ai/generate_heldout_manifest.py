import csv
import random
from pathlib import Path
from app.place_resolver_cli import load_komsco_population, load_local_env

def main():
    root = Path(__file__).resolve().parents[1]
    load_local_env(root)

    # 1. Load population
    population = load_komsco_population(root, None)
    
    # 2. Load baseline to exclude
    baseline_path = root / "ai/build/reports/naver-place-pipeline/komsco-i0000002-baseline-50-stable.manifest"
    baseline_ids = set()
    with open(baseline_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(row for row in f if not row.strip().startswith('#'))
        for row in reader:
            baseline_ids.add(row['external_merchant_id'])
            
    # 3. Filter population
    candidates = [
        ref for ref in population.references 
        if ref.external_merchant_id not in baseline_ids
    ]
    
    # 4. Sample 50 with seed 20260921
    random.seed(20260921)
    sampled = random.sample(candidates, 50)
    
    # 5. Write out to new manifest
    out_path = root / "ai/build/reports/naver-place-pipeline/qwen3.5-provider-fusion-heldout-50-v2.manifest"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["external_merchant_id", "restaurant_id", "komsco_name", "komsco_address", "komsco_lat", "komsco_lon", "legal_dong_name"])
        for ref in sampled:
            writer.writerow([
                ref.external_merchant_id,
                ref.restaurant_id,
                ref.komsco_name,
                ref.komsco_address,
                ref.komsco_latitude or "",
                ref.komsco_longitude or "",
                ref.legal_dong
            ])
            
    print(f"Wrote {len(sampled)} records to {out_path}")

if __name__ == "__main__":
    main()
