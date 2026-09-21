import csv
from collections import Counter
import sys

path = "ai/build/reports/naver-place-pipeline/qwen3.5-provider-fusion-heldout-50-v2.csv"
with open(path, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

statuses = Counter(r.get("resolve_status", "") for r in rows)
errors = Counter(r.get("error_reason", "") for r in rows)

print(f"Total Rows: {len(rows)}")
for k, v in statuses.items():
    print(f"Status: {k} = {v}")
    
print("Headers:", list(rows[0].keys()) if rows else "No rows")

lat_rank = [float(r["ranking_latency_ms"]) for r in rows if r.get("ranking_latency_ms")]
lat_sem = [float(r["semantic_latency_ms"]) for r in rows if r.get("semantic_latency_ms")]

if lat_rank:
    print(f"Avg Ranking Latency: {sum(lat_rank)/len(lat_rank):.2f} ms")
if lat_sem:
    print(f"Avg Semantic Latency: {sum(lat_sem)/len(lat_sem):.2f} ms")
    
timeouts = sum(1 for r in rows if r.get("timeout", "") == "true" or "timeout" in r.get("error_reason", "").lower())
print(f"Timeouts: {timeouts}")
